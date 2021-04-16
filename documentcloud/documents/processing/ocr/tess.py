# Standard Library
import ctypes
import ctypes.util
import locale
import os

locale.setlocale(locale.LC_ALL, "C")

script_dir = os.path.dirname(os.path.realpath(__file__))
LIB_PATH = os.path.join(script_dir, "tesseract/libtesseract.so.5")
DATA_PATH = os.path.join(script_dir, "tesseract/tessdata")


class TesseractError(Exception):
    pass


class Tesseract:
    _lib = None
    _api = None

    # pylint: disable=protected-access
    class TessBaseAPI(ctypes._Pointer):
        _type_ = type("_TessBaseAPI", (ctypes.Structure,), {})

    @classmethod
    def setup_lib(cls, lib_path=None):
        if cls._lib is not None:
            return
        if lib_path is None:
            lib_path = ctypes.util.find_library(LIB_PATH)
            if lib_path is None:
                raise TesseractError("tesseract library not found")
        cls._lib = lib = ctypes.CDLL(lib_path)

        # source:
        # https://github.com/tesseract-ocr/tesseract/
        #         blob/3.02.02/api/capi.h

        lib.TessBaseAPICreate.restype = cls.TessBaseAPI

        lib.TessBaseAPIDelete.restype = None  # void
        lib.TessBaseAPIDelete.argtypes = (cls.TessBaseAPI,)  # handle

        lib.TessDeleteResultRenderer.restype = None
        lib.TessDeleteResultRenderer.argtypes = (ctypes.c_void_p,)

        lib.TessBaseAPIInit4.argtypes = (
            cls.TessBaseAPI,  # handle
            ctypes.c_char_p,  # datapath
            ctypes.c_char_p,  # language
            ctypes.c_int,  # engine mode
            ctypes.c_void_p,  # configs
            ctypes.c_int,  # num configs
            ctypes.c_void_p,  # vars vec
            ctypes.c_void_p,  # vars values
            ctypes.c_int,  # vars size
            ctypes.c_int,
        )  # set only non debug params

        lib.TessBaseAPIGetDatapath.restype = ctypes.c_char_p
        lib.TessBaseAPIGetDatapath.argtypes = (cls.TessBaseAPI,)  # handle

        lib.TessBaseAPISetImage.restype = None
        lib.TessBaseAPISetImage.argtypes = (
            cls.TessBaseAPI,  # handle
            ctypes.c_void_p,  # imagedata
            ctypes.c_int,  # width
            ctypes.c_int,  # height
            ctypes.c_int,  # bytes_per_pixel
            ctypes.c_int,
        )  # bytes_per_line

        lib.TessBaseAPIGetUTF8Text.restype = ctypes.c_char_p
        lib.TessBaseAPIGetUTF8Text.argtypes = (cls.TessBaseAPI,)  # handle

        lib.TessBaseAPIGetHOCRText.restype = ctypes.c_char_p
        lib.TessBaseAPIGetHOCRText.argtypes = (cls.TessBaseAPI,)  # handle

        lib.TessPDFRendererCreate.restype = ctypes.c_void_p  # PDF renderer
        lib.TessPDFRendererCreate.argtypes = (
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int,
        )

        lib.TessResultRendererBeginDocument.restype = ctypes.c_int
        lib.TessResultRendererBeginDocument.argtypes = (
            ctypes.c_void_p,
            ctypes.c_char_p,
        )

        lib.TessResultRendererEndDocument.restype = ctypes.c_int
        lib.TessResultRendererEndDocument.argtypes = (ctypes.c_void_p,)

        lib.TessBaseAPIProcessPages.argtypes = (
            cls.TessBaseAPI,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_void_p,
        )

    def __init__(self, language="eng", datapath=DATA_PATH, lib_path=LIB_PATH):
        if self._lib is None:
            self.setup_lib(lib_path)
        self.pdf_renderer = None
        self._api = self._lib.TessBaseAPICreate()
        self.datapath = datapath
        if self._lib.TessBaseAPIInit4(
            self._api,
            datapath.encode("utf-8"),
            language.encode("utf-8"),
            1,
            None,
            0,
            None,
            None,
            0,
            1,
        ):
            raise TesseractError("initialization failed")

    def __del__(self):
        if not self._lib or not self._api:
            return
        if not getattr(self, "closed", False):
            if self.pdf_renderer:
                self._lib.TessDeleteResultRenderer(self.pdf_renderer)
            self._lib.TessBaseAPIDelete(self._api)
            self.closed = True

    def _check_setup(self):
        if not self._lib:
            raise TesseractError("lib not configured")
        if not self._api:
            raise TesseractError("api not created")

    def set_image(self, imagedata, width, height, bytes_per_pixel, bytes_per_line=None):
        self._check_setup()
        if bytes_per_line is None:
            bytes_per_line = width * bytes_per_pixel
        self._lib.TessBaseAPISetImage(
            self._api, imagedata, width, height, bytes_per_pixel, bytes_per_line
        )

    def get_utf8_text(self):
        self._check_setup()
        return self._lib.TessBaseAPIGetUTF8Text(self._api)

    def get_text(self):
        self._check_setup()
        result = self._lib.TessBaseAPIGetUTF8Text(self._api)
        return result.decode("utf-8")

    def get_hocr(self):
        self._check_setup()
        result = self._lib.TessBaseAPIGetHOCRText(self._api)
        return result.decode("utf-8")

    def create_pdf_renderer(self, output_file_base_name):
        self._check_setup()
        self.pdf_renderer = self._lib.TessPDFRendererCreate(
            os.path.abspath(output_file_base_name).encode("utf-8"),
            self.datapath.encode("utf-8"),
            1,
        )

    def render_pdf(self, image_path):
        self._check_setup()
        if not self.pdf_renderer:
            raise TesseractError("Set up renderer")

        if not self._lib.TessBaseAPIProcessPages(
            self._api,
            os.path.abspath(image_path).encode("utf-8"),
            None,
            0,
            self.pdf_renderer,
        ):
            raise TesseractError("render failed")
