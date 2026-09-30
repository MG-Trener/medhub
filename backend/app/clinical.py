"""Обязательная пометка добавляется сервером, независимо от ответа модели."""

AI_CONCLUSION_NOTICE = (
    'Данное предварительное заключение ИИ не является диагнозом. '
    'Врач обязан проверить его и несёт окончательную ответственность '
    'за диагноз, назначения и медицинские решения.'
)


def ai_notice():
    return {
        'type': 'preliminary_ai_conclusion',
        'is_diagnosis': False,
        'requires_doctor_review': True,
        'disclaimer': AI_CONCLUSION_NOTICE,
    }
