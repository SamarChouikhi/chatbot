import { FieldConfig } from './field-config';

// ── Utilisateur ───────────────────────────────────────────────────────────────

export const USER_FORM_FIELDS: FieldConfig[] = [
  {
    key: 'login', label: 'FORMS.USER.LOGIN', type: 'text',
    required: true, width: 'half', placeholder: 'FORMS.USER.LOGIN_PLACEHOLDER',
    minLength: 3, maxLength: 50
  },
  {
    key: 'pwd', label: 'FORMS.USER.PASSWORD', type: 'password',
    required: true, width: 'half', placeholder: '••••••••',
    minLength: 6
  },
  {
    key: 'phone', label: 'FORMS.USER.PHONE', type: 'text',
    width: 'half', placeholder: 'FORMS.USER.PHONE_PLACEHOLDER'
  },
  {
    key: 'isAdvisor', label: 'FORMS.USER.ROLE', type: 'select',
    width: 'half', defaultValue: 0,
    options: [
      { label: 'FORMS.USER.ROLE_STANDARD', value: 0 },
      { label: 'FORMS.USER.ROLE_ADVISOR',   value: 1 }
    ]
  },
  {
    key: 'gmtPlus', label: 'FORMS.USER.TIMEZONE', type: 'number',
    width: 'half', defaultValue: 1, min: -12, max: 14,
    hint: 'FORMS.USER.TIMEZONE_HINT'
  }
];

// ── Device (capteur) ──────────────────────────────────────────────────────────

/** Module requis pour pouvoir ajouter chaque type de capteur */
export const DEVICE_TYPE_MODULE_MAP: Record<number, string> = {
  1: 'énergie électrique',
  2: 'eau',
  3: 'gaz',
  4: 'carburant',
  5: 'équipements/capteurs',
  6: 'équipements/capteurs',
  7: 'équipements/capteurs'
};

export const DEVICE_FORM_FIELDS: FieldConfig[] = [
  {
    key: 'adresse', label: 'FORMS.DEVICE.ADDRESS', type: 'number',
    required: true, width: 'half', min: 0,
    hint: 'FORMS.DEVICE.ADDRESS_HINT'
  },
  {
    key: 'nom', label: 'FORMS.DEVICE.NAME', type: 'text',
    required: true, width: 'half', placeholder: 'FORMS.DEVICE.NAME_PLACEHOLDER'
  },
  {
    key: 'type', label: 'FORMS.DEVICE.TYPE', type: 'select',
    required: true, width: 'half',
    options: [
      { label: 'NAV.ELECTRICITY',        value: 1 },
      { label: 'NAV.WATER',              value: 2 },
      { label: 'NAV.GAS',                value: 3 },
      { label: 'NAV.FUEL',               value: 4 },
      { label: 'FORMS.DEVICE.TYPE_TEMP_HUMID', value: 5 },
      { label: 'FORMS.DEVICE.TYPE_PRESENCE',   value: 6 },
      { label: 'FORMS.DEVICE.TYPE_LEVEL',      value: 7 }
    ]
  },
  {
    key: 'id_espace', label: 'FORMS.DEVICE.SPACE', type: 'number',
    width: 'half', min: 1
  },
  {
    key: 'description', label: 'FORMS.DEVICE.DESCRIPTION', type: 'textarea',
    width: 'full', placeholder: 'FORMS.DEVICE.DESCRIPTION_PLACEHOLDER'
  }
];

// ── Règle d'alerte ────────────────────────────────────────────────────────────

export const ALERT_RULE_FIELDS: FieldConfig[] = [
  {
    key: 'label', label: 'FORMS.ALERT.RULE_NAME', type: 'text',
    required: true, width: 'full', placeholder: 'FORMS.ALERT.RULE_NAME_PLACEHOLDER'
  },
  {
    key: 'metric', label: 'FORMS.ALERT.METRIC', type: 'select',
    required: true, width: 'half',
    options: [
      { label: 'FORMS.ALERT.METRIC_THD',   value: 'THD' },
      { label: 'FORMS.ALERT.METRIC_COSFI', value: 'COSFI' },
      { label: 'FORMS.ALERT.METRIC_CONSO', value: 'CONSO' }
    ]
  },
  {
    key: 'operator', label: 'FORMS.ALERT.CONDITION', type: 'select',
    required: true, width: 'half',
    options: [
      { label: 'FORMS.ALERT.CONDITION_GT', value: '>' },
      { label: 'FORMS.ALERT.CONDITION_LT', value: '<' }
    ]
  },
  {
    key: 'threshold', label: 'FORMS.ALERT.THRESHOLD', type: 'number',
    required: true, width: 'half', min: 0,
    hint: 'FORMS.ALERT.THRESHOLD_HINT'
  },
  {
    key: 'severity', label: 'FORMS.ALERT.SEVERITY', type: 'select',
    required: true, width: 'half',
    options: [
      { label: 'FORMS.ALERT.SEVERITY_CRITICAL', value: 'critical' },
      { label: 'FORMS.ALERT.SEVERITY_HIGH',     value: 'high' },
      { label: 'FORMS.ALERT.SEVERITY_LOW',      value: 'low' }
    ]
  }
];
