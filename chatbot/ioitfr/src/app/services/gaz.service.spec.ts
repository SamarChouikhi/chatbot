import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { GazService } from './gaz.service';

describe('GazService', () => {
  let service: GazService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [GazService],
    });
    service = TestBed.inject(GazService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
