import { Component, input, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgClass } from '@angular/common';

@Component({
  selector: 'app-stepper',
  standalone: true,
  imports: [RouterLink, NgClass],
  templateUrl: './stepper.component.html',
  styleUrl: './stepper.component.scss',
})
export class StepperComponent {
  readonly activeStep = input<1 | 2 | 3>(1);
  readonly step3Done  = input(false);

  readonly step1Done   = computed(() => this.activeStep() > 1);
  readonly bar1Done    = computed(() => this.activeStep() > 1);
  readonly step2Active = computed(() => this.activeStep() === 2);
  readonly bar2Done    = computed(() => this.step3Done());
}
