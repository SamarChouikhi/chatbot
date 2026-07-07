import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Device {
  id: number;
  adresse: number;
  nom: string | null;
  description: string | null;
  type: number | null;
  id_espace: number | null;
  geometry: string | null;
  max_uptime: number | null;
  id_ls: number | null;
  is_general_meter: number | null;
  last_saved_index: number | null;
  login: string | null;
}

export interface DevicePage {
  data: Device[];
  total: number;
  page: number;
  size: number;
}

// Le backend Quarkus sérialise en camelCase (Jackson par défaut)
// → on mappe vers snake_case attendu par le composant
function mapDevice(d: any): Device {
  return {
    id:               d.id,
    adresse:          d.adresse,
    nom:              d.nom ?? null,
    description:      d.description ?? null,
    type:             d.type ?? null,
    id_espace:        d.idEspace   ?? d.id_espace   ?? null,
    geometry:         d.geometry   ?? null,
    max_uptime:       d.maxUptime  ?? d.max_uptime  ?? null,
    id_ls:            d.idLs       ?? d.id_ls       ?? null,
    is_general_meter: d.isGeneralMeter ?? d.is_general_meter ?? null,
    last_saved_index: d.lastSavedIndex ?? d.last_saved_index ?? null,
    login:            d.login ?? null,
  };
}

// Mappe snake_case → camelCase pour l'envoi au backend
function toBackend(d: Device): any {
  return {
    id:             d.id,
    adresse:        d.adresse,
    nom:            d.nom,
    description:    d.description,
    type:           d.type,
    idEspace:       d.id_espace,
    geometry:       d.geometry,
    maxUptime:      d.max_uptime,
    idLs:           d.id_ls,
    isGeneralMeter: d.is_general_meter,
    lastSavedIndex: d.last_saved_index,
    login:          d.login,
  };
}

@Injectable({ providedIn: 'root' })
export class DeviceService {

  private base = `${environment.apiUrl}/api/devices`;

  constructor(private http: HttpClient) {}

  list(page = 0, size = 9999, search?: string, type?: number): Observable<DevicePage> {
    let params = new HttpParams().set('page', page).set('size', size);
    if (search) params = params.set('search', search);
    if (type !== undefined && type !== null) params = params.set('type', type);
    return this.http.get<any>(this.base, { params }).pipe(
      map(res => ({
        data:  (res.data || []).map(mapDevice),
        total: res.total,
        page:  res.page,
        size:  res.size
      }))
    );
  }

  getOne(id: number, adresse: number): Observable<Device> {
    return this.http.get<any>(`${this.base}/${id}/${adresse}`).pipe(map(mapDevice));
  }

  create(device: Device): Observable<Device> {
    return this.http.post<any>(this.base, toBackend(device)).pipe(map(mapDevice));
  }

  update(id: number, adresse: number, device: Device): Observable<Device> {
    return this.http.put<any>(`${this.base}/${id}/${adresse}`, toBackend(device)).pipe(map(mapDevice));
  }

  delete(id: number, adresse: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}/${adresse}`);
  }

  listByUser(login: string): Observable<Device[]> {
    return this.http.get<any[]>(`${environment.apiUrl}/api/users/${login}/devices`).pipe(
      map(list => list.map(mapDevice))
    );
  }
}