export type FieldType =
  | 'text' | 'password' | 'email' | 'number'
  | 'date' | 'select' | 'textarea' | 'checkbox';

export interface FieldOption {
  label: string;
  value: any;
}

export interface FieldConfig {
  key: string;
  label: string;
  type: FieldType;
  placeholder?: string;
  defaultValue?: any;
  required?: boolean;
  min?: number;
  max?: number;
  minLength?: number;
  maxLength?: number;
  options?: FieldOption[];   // pour type 'select'
  width?: 'full' | 'half';  // layout en grille
  hint?: string;             // texte d'aide sous le champ
}
