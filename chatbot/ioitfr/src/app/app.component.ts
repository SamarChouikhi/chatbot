import { Component, OnInit } from '@angular/core';
import { LanguageService } from './core/services/language.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent implements OnInit {
  title = 'ioitfr';

  constructor(private lang: LanguageService) {}

  ngOnInit(): void {
    this.lang.init();
  }
}
