"""Recommandations rule-based (FR/EN/AR) quand le LLM est indisponible."""
from __future__ import annotations

import logging

logger = logging.getLogger('aria.reco_engine')

# ══════════════════════════════════════════════════════════════════════════════
# 9. FALLBACK RÈGLES
# ══════════════════════════════════════════════════════════════════════════════

_FALLBACK_TEXTS: dict[str, dict] = {
    'OVERCONSUMPTION': {
        'title_tpl'  : "Surconsommation {label} — {device_id}",
        'desc_tpl'   : "Consommation {actual_26h} {unit} sur 26h (+{deviation_pct}% vs baseline {baseline_p50_sum} {unit}). Pics : {peak_hours_str}.",
        'action'     : "Identifier les équipements actifs lors du pic. Vérifier les consignes de régulation.",
        'priority_fn': lambda s: 'critical' if s.get('deviation_pct', 0) > 100 else 'high' if s.get('deviation_pct', 0) > 50 else 'medium',
    },
    'OPTIMIZATION': {
        'title_tpl'  : "Optimisation nocturne — {device_id}",
        'desc_tpl'   : "Excès de {off_peak_excess} {unit} en heures creuses ({off_peak_hours}). Économie mensuelle estimée : {estimated_saving_tnd} TND.",
        'action'     : "Programmer des arrêts automatiques via le GTB pendant les heures creuses.",
        'priority_fn': lambda s: 'medium',
    },
    'BUDGET_ALERT': {
        'title_tpl'  : "Dépassement budgétaire {label}",
        'desc_tpl'   : "Projection fin de mois : {projected_total} {unit} (+{overage_pct}% vs {last_month_total} {unit} le mois précédent).",
        'action'     : "Activer les mesures d'économie sur les équipements non critiques.",
        'priority_fn': lambda s: 'critical' if s.get('overage_pct', 0) > 30 else 'high' if s.get('overage_pct', 0) > 15 else 'medium',
    },
    'MAINTENANCE': {
        'title_tpl'  : "Signal de dégradation — {device_id}",
        'desc_tpl'   : "Consommation en hausse continue 7 jours (+{trend_growth_pct}%). Valeur actuelle : {day7_value} {unit}/j vs {day1_value} {unit}/j.",
        'action'     : "Programmer une inspection préventive de l'équipement.",
        'priority_fn': lambda s: 'high' if s.get('trend_growth_pct', 0) > 40 else 'medium',
    },
    'LEAK_RISK': {
        'title_tpl'  : "Risque de fuite {label} — {device_id}",
        'desc_tpl'   : "Consommation anormale entre {hours_range} ({nocturnal_excess} {unit} au-dessus baseline). Coût mensuel : {estimated_saving_tnd} TND.",
        'action'     : "Inspecter le réseau de nuit. Tester l'étanchéité sur le circuit concerné.",
        'priority_fn': lambda s: 'critical',
    },
    'EFFICIENCY': {
        'title_tpl'  : "Efficacité carburant dégradée — {device_id}",
        'desc_tpl'   : "Véhicule {device_id} : {vehicle_conso_7d} {unit}/7j (+{over_pct}% vs flotte {fleet_mean_7d} {unit}).",
        'action'     : "Vérifier pression pneus, filtre à air. Programmer un entretien préventif.",
        'priority_fn': lambda s: 'high' if s.get('over_pct', 0) > 60 else 'medium',
    },
}

# Traductions statiques des gabarits de secours (pas d'appel LLM — le fallback existe
# précisément pour le cas où le LLM est indisponible, donc sa traduction doit l'être aussi).
_FALLBACK_TEXTS_EN: dict[str, dict] = {
    'OVERCONSUMPTION': {
        'title_tpl': "Overconsumption {label} — {device_id}",
        'desc_tpl' : "Consumption {actual_26h} {unit} over 26h (+{deviation_pct}% vs baseline {baseline_p50_sum} {unit}). Peaks: {peak_hours_str}.",
        'action'   : "Identify equipment active during the peak. Check regulation setpoints.",
    },
    'OPTIMIZATION': {
        'title_tpl': "Off-peak optimization — {device_id}",
        'desc_tpl' : "Excess of {off_peak_excess} {unit} during off-peak hours ({off_peak_hours}). Estimated monthly saving: {estimated_saving_tnd} TND.",
        'action'   : "Schedule automatic shutdowns via the BMS during off-peak hours.",
    },
    'BUDGET_ALERT': {
        'title_tpl': "Budget overrun {label}",
        'desc_tpl' : "End-of-month projection: {projected_total} {unit} (+{overage_pct}% vs {last_month_total} {unit} last month).",
        'action'   : "Activate saving measures on non-critical equipment.",
    },
    'MAINTENANCE': {
        'title_tpl': "Degradation signal — {device_id}",
        'desc_tpl' : "Consumption rising continuously over 7 days (+{trend_growth_pct}%). Current value: {day7_value} {unit}/day vs {day1_value} {unit}/day.",
        'action'   : "Schedule a preventive inspection of the equipment.",
    },
    'LEAK_RISK': {
        'title_tpl': "Leak risk {label} — {device_id}",
        'desc_tpl' : "Abnormal consumption between {hours_range} ({nocturnal_excess} {unit} above baseline). Monthly cost: {estimated_saving_tnd} TND.",
        'action'   : "Inspect the network at night. Test the circuit for leaks.",
    },
    'EFFICIENCY': {
        'title_tpl': "Degraded fuel efficiency — {device_id}",
        'desc_tpl' : "Vehicle {device_id}: {vehicle_conso_7d} {unit}/7d (+{over_pct}% vs fleet {fleet_mean_7d} {unit}).",
        'action'   : "Check tire pressure and air filter. Schedule preventive maintenance.",
    },
}

_FALLBACK_TEXTS_AR: dict[str, dict] = {
    'OVERCONSUMPTION': {
        'title_tpl': "استهلاك مفرط {label} — {device_id}",
        'desc_tpl' : "استهلاك {actual_26h} {unit} خلال 26 ساعة (+{deviation_pct}% مقارنة بالمرجع {baseline_p50_sum} {unit}). الذروات: {peak_hours_str}.",
        'action'   : "حدد المعدات النشطة أثناء الذروة. تحقق من إعدادات التحكم.",
    },
    'OPTIMIZATION': {
        'title_tpl': "تحسين خارج ساعات الذروة — {device_id}",
        'desc_tpl' : "فائض {off_peak_excess} {unit} خلال ساعات الانخفاض ({off_peak_hours}). التوفير الشهري المقدر: {estimated_saving_tnd} دينار.",
        'action'   : "برمج إيقافات تلقائية عبر نظام إدارة المبنى خلال ساعات الانخفاض.",
    },
    'BUDGET_ALERT': {
        'title_tpl': "تجاوز الميزانية {label}",
        'desc_tpl' : "توقع نهاية الشهر: {projected_total} {unit} (+{overage_pct}% مقارنة بـ {last_month_total} {unit} الشهر الماضي).",
        'action'   : "فعّل إجراءات التوفير على المعدات غير الحرجة.",
    },
    'MAINTENANCE': {
        'title_tpl': "إشارة تدهور — {device_id}",
        'desc_tpl' : "ارتفاع مستمر في الاستهلاك على مدى 7 أيام (+{trend_growth_pct}%). القيمة الحالية: {day7_value} {unit}/يوم مقابل {day1_value} {unit}/يوم.",
        'action'   : "برمج فحصاً وقائياً للمعدة.",
    },
    'LEAK_RISK': {
        'title_tpl': "خطر تسرب {label} — {device_id}",
        'desc_tpl' : "استهلاك غير طبيعي بين {hours_range} ({nocturnal_excess} {unit} فوق المرجع). التكلفة الشهرية: {estimated_saving_tnd} دينار.",
        'action'   : "افحص الشبكة ليلاً. اختبر شبكة الأنابيب بحثاً عن تسربات.",
    },
    'EFFICIENCY': {
        'title_tpl': "كفاءة وقود متدهورة — {device_id}",
        'desc_tpl' : "المركبة {device_id}: {vehicle_conso_7d} {unit}/7أيام (+{over_pct}% مقارنة بالأسطول {fleet_mean_7d} {unit}).",
        'action'   : "تحقق من ضغط الإطارات وفلتر الهواء. برمج صيانة وقائية.",
    },
}

_FALLBACK_NO_DATA_I18N = {
    'en': {
        'title_tpl': "Anomaly {label} detected — {dev}",
        'desc_tpl' : (
            "The Chronos model identified {count} abnormal point(s) "
            "with an anomaly score of {score:.2f}/1.0. "
            "Historical consumption data is insufficient to quantify the deviation — "
            "a preventive inspection is recommended."
        ),
    },
    'ar': {
        'title_tpl': "تم اكتشاف شذوذ {label} — {dev}",
        'desc_tpl' : (
            "حدد نموذج Chronos {count} نقطة (نقاط) غير طبيعية "
            "بدرجة شذوذ {score:.2f}/1.0. "
            "بيانات الاستهلاك التاريخية غير كافية لتحديد حجم الانحراف — "
            "يُنصح بإجراء فحص وقائي."
        ),
    },
}


_UNRELIABLE_UNITS_TEXTS = {
    'fr': {
        'title_tpl': "Écart anormal {label} — {dev}",
        'desc_tpl' : (
            "Consommation anormale par rapport à l'historique du compteur{pct}. "
            "Les volumes remontés sont incohérents avec l'unité attendue ({unit}) : "
            "l'impact financier n'est pas chiffré tant que le paramétrage du compteur n'est pas vérifié."
        ),
        'action'   : "Vérifier le paramétrage du compteur (unité, facteur d'échelle), puis inspecter l'équipement.",
    },
    'en': {
        'title_tpl': "Abnormal deviation {label} — {dev}",
        'desc_tpl' : (
            "Abnormal consumption compared with the meter's history{pct}. "
            "Reported volumes are inconsistent with the expected unit ({unit}): "
            "the financial impact is not estimated until the meter configuration is checked."
        ),
        'action'   : "Check the meter configuration (unit, scale factor), then inspect the equipment.",
    },
    'ar': {
        'title_tpl': "انحراف غير طبيعي {label} — {dev}",
        'desc_tpl' : (
            "استهلاك غير طبيعي مقارنة بسجل العداد{pct}. "
            "الكميات المرسلة لا تتوافق مع الوحدة المتوقعة ({unit}): "
            "لا يتم تقدير الأثر المالي قبل التحقق من إعدادات العداد."
        ),
        'action'   : "تحقق من إعدادات العداد (الوحدة، معامل القياس) ثم افحص المعدة.",
    },
}


def _unreliable_units_texts(signal: dict, domain: str) -> dict:
    ctx = {
        'label': signal.get('label', domain),
        'dev'  : signal.get('device_id', domain),
        'unit' : signal.get('unit', ''),
        'pct'  : f" (+{signal['deviation_pct']} %)" if signal.get('deviation_pct') is not None else '',
    }
    return {
        lang: {
            'title'      : tpl['title_tpl'].format(**ctx),
            'description': tpl['desc_tpl'].format(**ctx),
            'action'     : tpl['action'],
            'reasoning'  : None,
        }
        for lang, tpl in _UNRELIABLE_UNITS_TEXTS.items()
    }


def _build_fallback_i18n(signal: dict, domain: str, fb_action_fr: str) -> dict | None:
    """Construit les traductions en/ar du fallback règles — statiques, sans appel LLM.

    Le fallback existe pour le cas où le LLM est indisponible ; sa traduction ne
    peut donc pas dépendre du LLM non plus. `action` reste identique aux 3 langues
    quand la traduction n'est pas listée (verbe/consigne courte, moindre impact UX)."""
    rec_type = signal['rec_type']

    if signal.get('no_consumption_data'):
        score = signal.get('chronos_score', 0)
        count = signal.get('ad_anomaly_count', 0)
        dev   = signal.get('device_id', domain)
        label = signal.get('label', domain)
        out = {}
        for lang, tpl in _FALLBACK_NO_DATA_I18N.items():
            out[lang] = {
                'title'      : tpl['title_tpl'].format(label=label, dev=dev),
                'description': tpl['desc_tpl'].format(count=count, score=score),
                'action'     : fb_action_fr,
                'reasoning'  : None,
            }
        return out

    ctx = {**signal, 'peak_hours_str': ', '.join(f"{h}h" for h in signal.get('peak_hours', [])[:3])}
    out = {}
    for lang, table in (('en', _FALLBACK_TEXTS_EN), ('ar', _FALLBACK_TEXTS_AR)):
        fb = table.get(rec_type)
        if not fb:
            continue
        try:
            out[lang] = {
                'title'      : fb['title_tpl'].format(**ctx),
                'description': fb['desc_tpl'].format(**ctx),
                'action'     : fb['action'],
                'reasoning'  : None,
            }
        except Exception:
            continue
    return out or None


def _rule_based_fallback(signal: dict, domain: str) -> dict | None:
    rec_type = signal['rec_type']
    fb       = _FALLBACK_TEXTS.get(rec_type)
    if not fb:
        return None

    # Signals Chronos sans données de consommation : description générique sans chiffres inventés
    if signal.get('no_consumption_data'):
        score  = signal.get('chronos_score', 0)
        count  = signal.get('ad_anomaly_count', 0)
        dev    = signal.get('device_id', domain)
        label  = signal.get('label', domain)
        return {
            'priority'            : 'high' if score >= 0.75 else 'medium',
            'title'               : f"Anomalie {label} détectée — {dev}",
            'description'         : (
                f"Le modèle Chronos a identifié {count} point(s) anormal(aux) "
                f"avec un score d'anomalie de {score:.2f}/1.0. "
                f"Les données de consommation historiques sont insuffisantes pour quantifier l'écart — "
                f"une inspection préventive est recommandée."
            ),
            'action'              : fb['action'],
            'reasoning'           : None,
            'root_cause'          : None,
            'estimated_saving_tnd': None,
            'i18n'                : _build_fallback_i18n(signal, domain, fb['action']),
        }

    if signal.get('saving_unreliable'):
        texts = _unreliable_units_texts(signal, domain)
        fr    = texts.pop('fr')
        try:
            priority = fb['priority_fn'](signal)
        except Exception:
            priority = 'medium'
        return {
            'priority'            : priority,
            'title'               : fr['title'],
            'description'         : fr['description'],
            'action'              : fr['action'],
            'reasoning'           : None,
            'root_cause'          : None,
            'estimated_saving_tnd': None,
            'i18n'                : texts,
        }

    ctx = {**signal, 'peak_hours_str': ', '.join(f"{h}h" for h in signal.get('peak_hours', [])[:3])}
    try:
        return {
            'priority'            : fb['priority_fn'](signal),
            'title'               : fb['title_tpl'].format(**ctx),
            'description'         : fb['desc_tpl'].format(**ctx),
            'action'              : fb['action'],
            'reasoning'           : None,
            'root_cause'          : None,
            'estimated_saving_tnd': signal.get('estimated_saving_tnd'),
            'i18n'                : _build_fallback_i18n(signal, domain, fb['action']),
        }
    except Exception:
        return {
            'priority'            : 'medium',
            'title'               : f"{rec_type} — {signal.get('device_id', domain)}",
            'description'         : f"Anomalie détectée sur domaine {domain}.",
            'action'              : "Vérifier l'équipement concerné.",
            'reasoning'           : None,
            'root_cause'          : None,
            'estimated_saving_tnd': signal.get('estimated_saving_tnd'),
            'i18n'                : None,
        }
