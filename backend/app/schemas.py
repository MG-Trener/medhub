from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Register(Strict):
    name: str = Field(min_length=2, max_length=150)
    iin: str = Field(pattern=r'^[0-9]{12}$')
    email: str = Field(min_length=5, max_length=150, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=12, max_length=128)
    code: str = Field(default='', max_length=150)


class Login(Strict):
    email: str = Field(max_length=150)
    password: str = Field(max_length=128)


class PatientInput(Strict):
    name: str = Field(min_length=2, max_length=150)
    iin: str = Field(pattern=r'^\d{12}$')
    birth_date: date
    phone: str = Field(default='', max_length=30)
    sex: Literal['female', 'male', 'unknown'] = 'unknown'
    external_id: str | None = Field(default=None, max_length=100)
    recording_consent: bool = False
    cloud_consent: bool = False
    cloud_audio_consent: bool = False
    openai_audio_consent: bool = False

    @field_validator('birth_date')
    @classmethod
    def valid_date(cls, value):
        if value > date.today() or value.year < 1900:
            raise ValueError('Некорректная дата рождения')
        return value


class Consent(Strict):
    recording_consent: bool
    cloud_consent: bool
    cloud_audio_consent: bool = False
    openai_audio_consent: bool = False


class Segment(Strict):
    speaker: str = Field(pattern=r'^SPEAKER_\d{2}$')
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=10000)


class Consultation(Strict):
    complaints: str = Field(default='', max_length=15000)
    anamnesis: str = Field(default='', max_length=15000)
    examination: str = Field(default='', max_length=15000)
    diagnosis: str = Field(default='', max_length=10000)
    recommendations: str = Field(default='', max_length=15000)
    ai_conclusion: str = Field(default='', max_length=15000)


class EncounterPatch(Strict):
    version: int = Field(ge=1)
    fields: Consultation
    speaker_roles: dict[str, Literal['doctor', 'patient', 'nurse', 'unknown']] = Field(default_factory=dict, max_length=10)
    transcript: list[Segment] | None = Field(default=None, max_length=2000)


class PrivacyReview(Strict):
    version: int = Field(ge=1)
    segments: list[Segment] = Field(max_length=2000)


class Version(Strict):
    version: int = Field(ge=1)


class CloudAudio(Version):
    audio_reviewed: bool


class MuteAudio(Version):
    segment_indices: list[int] = Field(min_length=1, max_length=2000)


class IdentityStart(Strict):
    purpose: Literal['login', 'register', 'link'] = 'login'
    code: str = Field(default='', max_length=150)
    iin: str = Field(default='', pattern=r'^(?:[0-9]{12})?$')

    @model_validator(mode='after')
    def registration_iin_required(self):
        if self.purpose == 'register' and not self.iin:
            raise ValueError('Для регистрации укажите ИИН: 12 цифр')
        return self


class Signature(Strict):
    signature: str = Field(min_length=20, max_length=200000)
