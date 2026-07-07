import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RecoveryService } from './recovery.service';

describe('RecoveryService', () => {
  let service: RecoveryService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [RecoveryService],
    });
    service = TestBed.inject(RecoveryService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
