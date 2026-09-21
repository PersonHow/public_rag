#!/usr/bin/env bash
# setup_tls_loadbalancer.sh
#
# 一次性執行：把前端從 Cloud Run 的 *.run.app 移到外部 ALB，
# 以套用 SSL policy 修正 TLS 弱 cipher suite（資安弱掃 Medium）。
#
# 為什麼不用 Cloud Run 網域對應：那只換名字，TLS 仍由 Google Front End 終結、
# 用同一組預設 cipher，且沒有掛 SSL policy 的地方。必須自建 LB 才有那個開關。
#
# 執行（一次只跑一個 phase，中間有 12-24 小時的 DNS 等待，勿整份執行）：
#     bash setup_tls_loadbalancer.sh phase1         保留靜態 IP，印出要填的 DNS 內容
#     bash setup_tls_loadbalancer.sh phase2         建 LB 其餘元件（不必等 DNS）
#     bash setup_tls_loadbalancer.sh http_redirect  只重建 HTTP 轉址（phase2 中途失敗時）
#     bash setup_tls_loadbalancer.sh status         查 DNS 與憑證核發狀態
#     bash setup_tls_loadbalancer.sh verify         驗證弱 cipher 已被拒絕、網站正常
#     bash setup_tls_loadbalancer.sh phase3         正式切換（更新 CORS、關閉 run.app）
#     bash setup_tls_loadbalancer.sh rollback       緊急回滾，恢復 run.app 直連
#     bash setup_tls_loadbalancer.sh harden_custom  備援：RESTRICTED 不如預期時改用 CUSTOM
#
# ⚠ 需要 compute.networkAdmin（建 LB）與 run.admin（改 ingress 與環境變數）權限。
# ⚠ phase3 會讓兩種格式的 run.app 網址同時失效，執行前確認無外部串接仍在使用。

set -euo pipefail

PROJECT=shaped-totem-468106-g3
REGION=asia-east1
FE_SVC=public-rag-frontend
BE_SVC=public-rag-backend
DOMAIN=ai-agent.onceagain.tw
OLD_URL=https://public-rag-frontend-550905952099.asia-east1.run.app

gcloud config set project "$PROJECT" >/dev/null


phase1() {
  echo "── 保留全域靜態 IP ──"
  gcloud compute addresses create rag-fe-ip \
    --global --ip-version=IPV4 \
    --description="Static IP for ${DOMAIN} external ALB"

  local ip
  ip=$(gcloud compute addresses describe rag-fe-ip --global --format="value(address)")

  cat <<EOF

╔══════════════════════════════════════════════════════╗
  請到網路中文「DNS紀錄設定」新增一列：

     記錄類型      A
     主機名稱/別名  AI-Agent
     IP/域名       ${ip}
     優先權/權重    留空

  不要動到：MX 五筆、google._domainkey 的 TXT、
            apex 的 A (192.0.78.150 / .254 = WordPress 官網)
╚══════════════════════════════════════════════════════╝

設完 DNS 就可以接著跑 phase2，不用等 DNS 生效。
EOF
}


phase2() {
  echo "── 1/7 Serverless NEG ──"
  gcloud compute network-endpoint-groups create rag-fe-neg \
    --region="$REGION" \
    --network-endpoint-type=serverless \
    --cloud-run-service="$FE_SVC"

  echo "── 2/7 Backend service ──"
  gcloud compute backend-services create rag-fe-bs \
    --global --load-balancing-scheme=EXTERNAL_MANAGED
  gcloud compute backend-services add-backend rag-fe-bs \
    --global \
    --network-endpoint-group=rag-fe-neg \
    --network-endpoint-group-region="$REGION"

  echo "── 3/7 URL map ──"
  gcloud compute url-maps create rag-fe-map --default-service=rag-fe-bs

  echo "── 4/7 SSL policy（這一步才是真正修掉漏洞的地方）──"
  # RESTRICTED：只留 ECDHE + GCM/CHACHA，排除所有 CBC-SHA 與 TLS_RSA（無前向保密）
  # 若這行報錯說不認得 --global，把 --global 拿掉重跑（舊版 gcloud 的 ssl-policies 本來就只有全域）
  gcloud compute ssl-policies create tls-restricted \
    --profile=RESTRICTED --min-tls-version=1.2 --global
  echo "   實際涵蓋的 cipher："
  gcloud compute ssl-policies describe tls-restricted --global \
    --format="value(enabledFeatures)" | tr ';' '\n' | sed 's/^/     /'

  echo "── 5/7 Google-managed 憑證 ──"
  gcloud compute ssl-certificates create rag-fe-cert \
    --domains="$DOMAIN" --global

  echo "── 6/7 Target HTTPS proxy（把 SSL policy 掛上去）──"
  gcloud compute target-https-proxies create rag-fe-https-proxy \
    --url-map=rag-fe-map \
    --ssl-certificates=rag-fe-cert \
    --ssl-policy=tls-restricted \
    --global

  echo "── 7/7 Forwarding rules（443 + 80 轉址）──"
  gcloud compute forwarding-rules create rag-fe-https-fr \
    --global --target-https-proxy=rag-fe-https-proxy --ports=443 \
    --address=rag-fe-ip --load-balancing-scheme=EXTERNAL_MANAGED

  http_redirect

  echo
  echo "建置完成。接下來等 DNS + 憑證，用 'bash rag-lb.sh status' 查。"
}


# HTTP(80) → HTTPS(301) 轉址。phase2 會自動呼叫，失敗時可單獨重跑。
# 注意：url-maps import 的 schema 不接受 kind 欄位，加了會驗證失敗。
http_redirect() {
  local tmp; tmp=$(mktemp)
  cat > "$tmp" <<'EOF'
name: rag-fe-redirect-map
defaultUrlRedirect:
  redirectResponseCode: MOVED_PERMANENTLY_DEFAULT
  httpsRedirect: true
EOF
  gcloud compute url-maps import rag-fe-redirect-map --source="$tmp" --global --quiet
  rm -f "$tmp"

  gcloud compute target-http-proxies create rag-fe-http-proxy \
    --url-map=rag-fe-redirect-map --global
  gcloud compute forwarding-rules create rag-fe-http-fr \
    --global --target-http-proxy=rag-fe-http-proxy --ports=80 \
    --address=rag-fe-ip --load-balancing-scheme=EXTERNAL_MANAGED
}


status() {
  echo "── DNS ──"
  echo -n "  ${DOMAIN} → "; dig +short A "$DOMAIN" | tr '\n' ' '; echo
  echo -n "  LB IP      → "
  gcloud compute addresses describe rag-fe-ip --global --format="value(address)"

  echo "── 憑證 ──"
  gcloud compute ssl-certificates describe rag-fe-cert --global \
    --format="value(managed.status, managed.domainStatus)"
  echo "  (PROVISIONING = 還在等 DNS，正常；要等到 ACTIVE)"
}


# 回傳實際協商到的 cipher 名稱；握手失敗回空字串。
#
# 判準必須用 "New, ..., Cipher is ..." 這一行，因為它在三種情境都會出現：
#   New, (NONE), Cipher is (NONE)                → 握手失敗（即該套件被拒絕）
#   New, TLSv1.2, Cipher is ECDHE-RSA-AES256-... → 協商成功
#   New, TLSv1.3, Cipher is TLS_AES_256_GCM_...  → 協商成功
# 不能用 "Cipher    :" 那一行：TLS1.3 連線不會印它，會把正常連線誤判成失敗；
# 也不能只判斷「字串非空」：失敗時那行仍存在，只是值為 (NONE)/0000。
# 注意：套件被拒絕時 openssl 會以非零狀態退出，在 set -e + pipefail 下會直接
# 終止整個腳本 —— 也就是「測試成功」反而讓腳本掛掉。故兩處都要 || true。
_negotiated() {
  local out
  out=$(openssl s_client -connect "${DOMAIN}:443" -servername "$DOMAIN" "$@" </dev/null 2>&1) || true
  printf '%s\n' "$out" | grep -m1 '^New,' | sed 's/.*Cipher is //' | sed 's/^(NONE)$//' || true
}


verify() {
  local ok=1

  echo "── 0. 前置檢查（連不上時下面的「拒絕」全是假的）──"
  local ips; ips=$(dig +short A "$DOMAIN" | tr '\n' ' ')
  if [ -z "${ips// /}" ]; then
    echo "   ✗ $DOMAIN 尚未解析到 IP，DNS 還沒生效。中止。"; return 1
  fi
  echo "   ✓ DNS：$ips"

  local dflt; dflt=$(_negotiated)
  if [ -z "$dflt" ]; then
    echo "   ✗ TLS 握手失敗，憑證可能仍在 PROVISIONING。中止。"
    echo "     先跑：bash $(basename "$0") status"; return 1
  fi
  echo "   ✓ 預設協商：$dflt"

  echo "── 1. 被點名的六個弱套件（全部必須拒絕）──"
  local c r
  for c in ECDHE-RSA-AES128-SHA ECDHE-RSA-AES256-SHA AES128-GCM-SHA256 \
           AES256-GCM-SHA384 AES128-SHA AES256-SHA; do
    r=$(_negotiated -tls1_2 -cipher "$c")
    if [ -z "$r" ]; then printf '   %-22s ✓ 拒絕\n' "$c"
    else printf '   %-22s ✗ 仍被接受 (%s)\n' "$c" "$r"; ok=0; fi
  done

  echo "── 2. 對照組（證明測試有鑑別力，不是全部連不上）──"
  r=$(_negotiated -tls1_2 -cipher ECDHE-RSA-AES256-GCM-SHA384)
  if [ "$r" = ECDHE-RSA-AES256-GCM-SHA384 ]; then
    echo "   ✓ 合規套件可協商 —— 上面的「拒絕」是真的"
  else
    echo "   ✗ 連合規套件都不通，上面的結果不可信"; ok=0
  fi

  echo "── 3. 舊版 TLS（min TLS 1.2 應擋掉 1.0/1.1）──"
  local v
  for v in tls1 tls1_1; do
    [ -z "$(_negotiated -$v)" ] && echo "   $v ✓ 拒絕" || { echo "   $v ✗ 仍接受"; ok=0; }
  done

  echo "── 4. 應用層 ──"
  local h b; h=$(mktemp); b=$(mktemp)
  curl -s -D "$h" -o "$b" "https://${DOMAIN}/"
  echo -n "   HTTPS 首頁：      "; head -1 "$h"
  echo -n "   HTTP→HTTPS：      "; curl -s -o /dev/null -w '%{http_code} → %{redirect_url}\n' "http://${DOMAIN}/"
  echo -n "   /api/ 可達：      "; curl -s -o /dev/null -w '%{http_code}\n' "https://${DOMAIN}/api/health"
  # grep -c 找到 0 筆會回傳退出碼 1，在 set -e 下正好是「結果正確」時腳本掛掉
  echo -n "   unsafe-inline（要 0）：" ; grep -ci 'unsafe-inline' "$h" || true

  # CSP nonce：header 與 body 的值必須一致，否則樣式會整個掉光
  local nh nb
  nh=$(grep -i '^content-security-policy:' "$h" | grep -o 'nonce-[a-f0-9]*' | head -1 | cut -d- -f2 || true)
  nb=$(grep -o 'ngcspnonce="[a-f0-9]*"' "$b" | head -1 | cut -d'"' -f2 || true)
  if [ -n "$nh" ] && [ "$nh" = "$nb" ]; then echo "   CSP nonce：        ✓ 一致 ($nh)"
  else echo "   CSP nonce：        ✗ 不一致 header=$nh body=$nb"; ok=0; fi
  rm -f "$h" "$b"

  echo
  [ "$ok" = 1 ] && echo "✓ 全數通過，可以進 phase3" || echo "✗ 有項目未通過，不要進 phase3"
  [ "$ok" = 1 ]
}


phase3() {
  echo "⚠  這一步會讓舊的 run.app 網址失效。確認 verify 全過了嗎？"
  read -r -p "   輸入 yes 繼續：" a; [ "$a" = yes ] || { echo "已取消"; return 1; }

  echo "── 1/2 更新後端 CORS_ORIGINS（新舊網域都留）──"
  # 兩個陷阱：
  # 1. 必須用 --update-env-vars。--set-env-vars 是整批取代，會清掉後端全部 30 個
  #    環境變數（DATABASE_URL、JWT_SECRET_KEY、INTERNAL_TOKEN...），服務會起不來。
  # 2. --update-env-vars 預設以逗號分隔「不同變數」，但 CORS_ORIGINS 的值本身就含
  #    逗號（兩個 origin），會被誤切。^@^ 前綴改用 @ 當分隔符，見 gcloud topic escaping。
  gcloud run services update "$BE_SVC" --region="$REGION" \
    --update-env-vars="^@^CORS_ORIGINS=https://${DOMAIN},${OLD_URL}"

  echo "── 2/2 關閉 run.app 直連（新舊兩種格式會一起失效）──"
  gcloud run services update "$FE_SVC" --region="$REGION" \
    --ingress=internal-and-cloud-load-balancing

  echo "完成。請重跑 verify，並確認舊網址已無法直連。"
}


rollback() {
  echo "── 還原 run.app 直連 ──"
  gcloud run services update "$FE_SVC" --region="$REGION" --ingress=all
  echo "舊網址已恢復。LB 仍在，不影響。"
}


# 備援：萬一 RESTRICTED 實際內容不如預期，改用 CUSTOM 明列六個 ECDHE+AEAD 套件。
# 這六個是 GCP 支援清單裡唯一同時具備前向保密與 AEAD 的，被點名的八個全部排除。
harden_custom() {
  gcloud compute ssl-policies update tls-restricted --global \
    --profile=CUSTOM --min-tls-version=1.2 \
    --custom-features=TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256,TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256
  gcloud compute ssl-policies describe tls-restricted --global --format="value(enabledFeatures)" | tr ';' '\n'
}


case "${1:-}" in
  phase1|phase2|http_redirect|status|verify|phase3|rollback|harden_custom) "$1" ;;
  *) sed -n '2,14p' "$0"; exit 1 ;;
esac
