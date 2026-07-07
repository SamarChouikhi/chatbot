import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { AriaService } from './aria.service';
import { environment } from '../../environments/environment';

describe('AriaService', () => {
  let service: AriaService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [AriaService],
    });
    localStorage.clear();
    sessionStorage.clear();
    service = TestBed.inject(AriaService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
    sessionStorage.clear();
  });

  it('devrait être créé', () => {
    expect(service).toBeTruthy();
  });

  // ── getCurrentUserId() ─────────────────────────────────────────────────────

  describe('getCurrentUserId()', () => {
    it('retourne "default_user" si aucun user en storage', () => {
      expect(service.getCurrentUserId()).toBe('default_user');
    });

    it('retourne le login depuis localStorage', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'alice', role: 'ADMIN' }));
      expect(service.getCurrentUserId()).toBe('alice');
    });

    it('retourne le login depuis sessionStorage si absent de localStorage', () => {
      sessionStorage.setItem('user', JSON.stringify({ login: 'bob', role: 'EMPLOYEE' }));
      expect(service.getCurrentUserId()).toBe('bob');
    });

    it('retourne "default_user" si le JSON est invalide', () => {
      localStorage.setItem('user', '{invalid}');
      expect(service.getCurrentUserId()).toBe('default_user');
    });

    it('retourne "default_user" si login est absent de l\'objet', () => {
      localStorage.setItem('user', JSON.stringify({ role: 'ADMIN' }));
      expect(service.getCurrentUserId()).toBe('default_user');
    });
  });

  // ── getCurrentUserRole() ───────────────────────────────────────────────────

  describe('getCurrentUserRole()', () => {
    it('retourne "EMPLOYEE" si aucun user en storage', () => {
      expect(service.getCurrentUserRole()).toBe('EMPLOYEE');
    });

    it('retourne le rôle depuis localStorage', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'alice', role: 'SUPER_ADMIN' }));
      expect(service.getCurrentUserRole()).toBe('SUPER_ADMIN');
    });

    it('retourne "EMPLOYEE" si le JSON est invalide', () => {
      localStorage.setItem('user', 'bad-json');
      expect(service.getCurrentUserRole()).toBe('EMPLOYEE');
    });

    it('retourne "EMPLOYEE" si role est absent', () => {
      localStorage.setItem('user', JSON.stringify({ login: 'alice' }));
      expect(service.getCurrentUserRole()).toBe('EMPLOYEE');
    });
  });

  // ── ask() — structure de la requête HTTP ──────────────────────────────────

  describe('ask()', () => {
    it('envoie une requête POST à /chat avec question et userId', () => {
      service.ask('Température actuelle ?', undefined, 'alice').subscribe();

      const req = httpMock.expectOne(`${environment.ariaApiUrl}/chat`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body.question).toBe('Température actuelle ?');
      expect(req.request.body.userId).toBe('alice');
      req.flush({ answer: 'ok', backend: 'ollama', level: 'data', duration: 1, thread_id: 't1', message_id: 1, confidence: null });
    });

    it('inclut threadId si fourni', () => {
      service.ask('test', 'thread-abc', 'user1').subscribe();

      const req = httpMock.expectOne(`${environment.ariaApiUrl}/chat`);
      expect(req.request.body.threadId).toBe('thread-abc');
      req.flush({ answer: '', backend: '', level: '', duration: 0, thread_id: '', message_id: null, confidence: null });
    });

    it('utilise "default_user" comme userId par défaut', () => {
      service.ask('test').subscribe();

      const req = httpMock.expectOne(`${environment.ariaApiUrl}/chat`);
      expect(req.request.body.userId).toBe('default_user');
      req.flush({ answer: '', backend: '', level: '', duration: 0, thread_id: '', message_id: null, confidence: null });
    });
  });

  // ── postFeedback() ─────────────────────────────────────────────────────────

  describe('postFeedback()', () => {
    it('envoie une requête POST à /feedback avec les bons paramètres', () => {
      service.postFeedback(42, 'th-1', 'up', 'alice').subscribe();

      const req = httpMock.expectOne(`${environment.ariaApiUrl}/feedback`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body.message_id).toBe(42);
      expect(req.request.body.thread_id).toBe('th-1');
      expect(req.request.body.vote).toBe('up');
      expect(req.request.body.user_id).toBe('alice');
      req.flush({ status: 'ok' });
    });
  });

  // ── getThreads() ───────────────────────────────────────────────────────────

  describe('getThreads()', () => {
    it('envoie une requête GET à /threads avec user_id et limit', () => {
      service.getThreads('alice', 10).subscribe();

      const req = httpMock.expectOne(r => r.url.includes('/threads'));
      expect(req.request.method).toBe('GET');
      expect(req.request.params.get('user_id')).toBe('alice');
      expect(req.request.params.get('limit')).toBe('10');
      req.flush([]);
    });
  });

  // ── deleteThread() ─────────────────────────────────────────────────────────

  describe('deleteThread()', () => {
    it('envoie une requête DELETE à /threads/:id', () => {
      service.deleteThread('thread-123').subscribe();

      const req = httpMock.expectOne(`${environment.ariaApiUrl}/threads/thread-123`);
      expect(req.request.method).toBe('DELETE');
      req.flush({});
    });
  });
});
