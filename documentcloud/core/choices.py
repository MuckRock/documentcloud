# Django
from django.utils.translation import ugettext_lazy as _

# Third Party
from djchoices import ChoiceItem, DjangoChoices


class Language(DjangoChoices):
    # pylint: disable=no-init
    arabic = ChoiceItem("ara", _("Arabic"))
    chinese_simplified = ChoiceItem("zho", _("Chinese (Simplified)"))
    chinese_traditional = ChoiceItem("tra", _("Chinese (Traditional)"))
    croatian = ChoiceItem("hrv", _("Croatian"))
    danish = ChoiceItem("dan", _("Danish"))
    dutch = ChoiceItem("nld", _("Dutch"))
    english = ChoiceItem("eng", _("English"))
    french = ChoiceItem("fra", _("French"))
    german = ChoiceItem("deu", _("German"))
    hebrew = ChoiceItem("heb", _("Hebrew"))
    hungarian = ChoiceItem("hun", _("Hungarian"))
    indonesian = ChoiceItem("ind", _("Indonesian"))
    italian = ChoiceItem("ita", _("Italian"))
    japanese = ChoiceItem("jpn", _("Japanese"))
    korean = ChoiceItem("kor", _("Korean"))
    norwegian = ChoiceItem("nor", _("Norwegian"))
    portuguese = ChoiceItem("por", _("Portuguese"))
    romanian = ChoiceItem("ron", _("Romanian"))
    russian = ChoiceItem("rus", _("Russian"))
    spanish = ChoiceItem("spa", _("Spanish"))
    swedish = ChoiceItem("swe", _("Swedish"))
    ukrainian = ChoiceItem("ukr", _("Ukrainian"))

    user = [
        danish.value,
        english.value,
        french.value,
        russian.value,
        spanish.value,
        ukrainian.value,
    ]

    # For user facing purposes, documents are considered to have only a language.
    # In reality documents possess two distinct properties a language
    # and a written script. The former can be represented by ISO-639-2
    # language codes and the latter by ISO-15924 script codes.
    #
    # In almost all cases the script of a document can be inferred based
    # on its language (Ukrainian language documents are all written using Cyrillic)
    # with the exception of Chinese which for political and historical reasons
    # possesses two written scripts, traditional and simplified.
    #
    # The Tesseract OCR system requires knowing both language and script in order
    # to be able to correctly process documents, and consequently has two separate
    # langauge packages for Chinese, 'chi-tra' and 'chi-sim'.  All other language
    # packs are identical to their ISO-639-2 code.
    @classmethod
    def ocr_name(cls, code):
        if code == cls.chinese_traditional:
            return "chi_tra"
        elif code == cls.chinese_simplified:
            return "chi_sim"
        else:
            return code
