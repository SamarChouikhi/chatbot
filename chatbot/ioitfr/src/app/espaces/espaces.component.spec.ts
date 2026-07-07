import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { NO_ERRORS_SCHEMA } from '@angular/core';
import { EspacesComponent } from './espaces.component';

describe('EspacesComponent', () => {
  let component: EspacesComponent;
  let fixture: ComponentFixture<EspacesComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [EspacesComponent],
      imports: [HttpClientTestingModule, RouterTestingModule],
      schemas: [NO_ERRORS_SCHEMA],
    }).compileComponents();
    fixture   = TestBed.createComponent(EspacesComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
