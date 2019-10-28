# Standard Library
import ctypes
import os
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_char_p,
    c_double,
    c_float,
    c_int,
    c_ubyte,
    c_uint8,
    c_uint32,
    c_ulong,
    c_ushort,
    c_void_p,
    cdll,
)

# Third Party
import PIL.Image

c_float_p = POINTER(c_float)
c_ushort_p = POINTER(c_ushort)
c_ubyte_p = POINTER(c_ubyte)
c_uint8_p = POINTER(c_uint8)

INT_MAX = 2147483647

# Adapted from https://github.com/gersonkurz/pydfium


class FPDFLibraryConfig(Structure):
    _fields_ = [
        ("version", c_int),
        ("user_font_paths", c_void_p),  # not supported yet
        ("isolate", c_void_p),
        ("v8embedder_slot", c_int),
    ]


class FPDFFileWrite(Structure):
    _fields_ = [
        ("version", c_int),
        ("WriteBlock", CFUNCTYPE(c_int, c_void_p, c_void_p, c_ulong)),
    ]


class FPDFFileAccess(Structure):
    _fields_ = [
        ("m_FileLen", c_ulong),
        ("m_GetBlock", CFUNCTYPE(c_int, c_void_p, c_ulong, c_ubyte_p, c_ulong)),
        ("m_Param", c_void_p),
    ]


class Bitmap:
    def __init__(self, workspace, page, width=None, height=None):
        self.workspace = workspace
        self.page = page.page

        # Calculate missing dimensions, filling in with aspect ratio
        if width is None and height is None:
            width = page.width
            height = page.height
        if width is None:
            width = height / page.height * page.width
        if height is None:
            height = width / page.width * page.height

        self.width = round(width)
        self.height = round(height)
        self.bitmap = self.workspace.fpdf_bitmap_create(self.width, self.height, 0)
        assert self.bitmap != 0

        # Render white background
        self.workspace.fpdf_bitmap_fill_rect(
            self.bitmap, 0, 0, self.width, self.height, 0xFFFFFFFF
        )

        # Render with print settings and no rotation
        self.workspace.fpdf_render_page_bitmap(
            self.bitmap, self.page, 0, 0, self.width, self.height, 0, 0x800
        )

        stride = self.workspace.fpdf_bitmap_get_stride(self.bitmap)

        # Safety checks to make sure that the bitmap is rendered correctly
        if (
            (stride < 0)
            or (self.width > INT_MAX / self.height)
            or ((stride * self.height) > (INT_MAX / 3))
        ):
            raise RuntimeError("Invalid bitmap")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.workspace.fpdf_bitmap_destroy(self.bitmap)
        del self.bitmap

    def render(self, storage, filename, image_format="gif"):
        # Use PIL
        bufflen = self.width * self.height * 4
        bitmap = self.workspace.fpdf_get_bitmap_buffer(self.bitmap)
        bitmap = ctypes.cast(bitmap, ctypes.POINTER((bufflen * ctypes.c_ubyte)))

        img = PIL.Image.frombuffer(
            "RGBA", (self.width, self.height), bitmap.contents, "raw", "RGBA", 0, 1
        )
        # pylint: disable=invalid-name
        b, g, r, _a = img.split()
        img = PIL.Image.merge("RGB", (r, g, b))
        with storage.open(filename, "wb") as image_file:
            img.save(image_file, format=image_format)
        return img


class Document:
    def __init__(self, workspace, doc):
        self.workspace = workspace
        self.doc = doc
        self.loaded_fonts = []

        self._serif = None
        self._sans = None
        self._monospace = None

        assert self.doc != 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        for font in self.loaded_fonts:
            self.workspace.fpdf_font_close(font)
        self.workspace.fpdf_close_document(self.doc)
        del self.doc

    def load_page(self, page_number):
        result = self.workspace.fpdf_load_page(self.doc, page_number)
        if not result:
            error = self.workspace.pdfium.FPDF_GetLastError()
            assert False, f"ERROR {error}: unable to load page"

        return Page(self.workspace, self, result)

    def add_page(self, width, height):
        return Page(
            self.workspace,
            self,
            self.workspace.fpdf_page_new(self.doc, self.page_count, width, height),
        )

    def load_font_from_file(self, filename):
        with open(filename, "rb") as font_file:
            contents = bytearray(font_file.read())
        buff_len = len(contents)
        font_buffer = (ctypes.c_uint8 * buff_len).from_buffer(contents)
        font = self.workspace.fpdf_text_load_font(self.doc, font_buffer, buff_len, 2, 0)
        self.loaded_fonts.append(font)
        return font

    @property
    def serif_font(self):
        if self._serif is None:
            self._serif = self.load_font_from_file("times_new_roman.ttf")
        return self._serif

    @property
    def sans_font(self):
        if self._sans is None:
            self._sans = self.load_font_from_file("helvetica.ttf")
        return self._sans

    @property
    def monospace_font(self):
        if self._monospace is None:
            self._monospace = self.load_font_from_file("courier.ttf")
        return self._monospace

    def save(self, filename):
        with open(filename, "wb") as doc_file:

            @CFUNCTYPE(c_int, c_void_p, c_void_p, c_ulong)
            def write_block(_fpdf_filewrite, p_data, size):
                data = ctypes.cast(p_data, ctypes.POINTER((size * ctypes.c_ubyte)))
                doc_file.write(data.contents)
                return 1

            # Write with incremental rendering
            file_writer = FPDFFileWrite(1, write_block)
            assert (
                self.workspace.fpdf_save_as_copy(self.doc, byref(file_writer), 1) == 1
            )

    @property
    def page_count(self):
        return self.workspace.fpdf_get_page_count(self.doc)


class Page:
    def __init__(self, workspace, doc, page):
        self.workspace = workspace
        self.doc = doc
        self.page = page
        self.page_objects = []
        assert self.page != 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.workspace.fpdf_close_page(self.page)
        del self.page

    def get_bitmap(self, width, height):
        return Bitmap(self.workspace, self, width, height)

    def get_bounds(self, page_obj):
        left = c_float(0)
        bottom = c_float(0)
        right = c_float(0)
        top = c_float(0)
        assert (
            self.workspace.fpdf_page_obj_get_bounds(
                page_obj, byref(left), byref(bottom), byref(right), byref(top)
            )
            == 1
        )
        return (left, bottom, right, top)

    def set_desired_transform(self, page_object, x, y, width, height):
        # Get the bounds of the text object
        (left, bottom, right, top) = self.get_bounds(page_object)

        # Transform to origin
        self.workspace.fpdf_page_obj_transform(
            page_object, 1.0, 0.0, 0.0, 1.0, left.value * -1.0, bottom.value * -1.0
        )

        # Scale to size
        width_scale = width / (right.value - left.value)
        height_scale = 1 if height == -1 else height / (top.value - bottom.value)
        self.workspace.fpdf_page_obj_transform(
            page_object, width_scale, 0, 0, height_scale, 0, 0
        )

        # Transform to desired position
        self.workspace.fpdf_page_obj_transform(
            page_object, 1.0, 0.0, 0.0, 1.0, x, self.height - y - height
        )

    def add_bitmap(self, bitmap, x, y, width, height):
        image_obj = self.workspace.fpdf_page_obj_new_image_obj(self.doc.doc)
        assert (
            self.workspace.fpdf_image_obj_set_bitmap(
                self.page, 0, image_obj, bitmap.bitmap
            )
            == 1
        )
        self.set_desired_transform(image_obj, x, y, width, height)
        self.workspace.fpdf_insert_object(self.page, image_obj)
        del image_obj

    def add_sized_text(self, text, x, y, width, height):
        text_obj = self.workspace.fpdf_page_obj_create_text_obj(
            self.doc.doc, self.doc.sans_font, height
        )

        # Set the text
        encoded = text.encode("utf-16le") + b"\x00\x00"
        assert self.workspace.fpdf_text_set_text(text_obj, c_char_p(encoded)) == 1

        # Transform the text
        self.set_desired_transform(text_obj, x, y + height, width, -1)

        # Set transparent fill
        assert self.workspace.fpdf_page_obj_set_fill_color(text_obj, 0, 0, 0, 0) == 1

        # Insert the object into the page.
        self.workspace.fpdf_insert_object(self.page, text_obj)
        del text_obj

    def save(self):
        assert self.workspace.fpdf_page_generate_content(self.page) == 1

    @property
    def width(self):
        return self.workspace.fpdf_get_page_width(self.page)

    @property
    def height(self):
        return self.workspace.fpdf_get_page_height(self.page)

    @property
    def text(self):
        text_page = self.workspace.fpdf_text_load_page(self.page)
        num_chars = self.workspace.fpdf_text_count_chars(text_page)
        char_buffer = (c_ushort * num_chars)()
        chars_read = self.workspace.fpdf_text_get_text(
            text_page, 0, num_chars, char_buffer
        )
        assert (
            chars_read >= num_chars
        ), f"Text extraction error: {chars_read} read, {num_chars} expected"
        self.workspace.fpdf_text_close_page(text_page)

        text_content = ctypes.string_at(char_buffer, num_chars * 2)
        # Decode and normalize line endings
        return text_content.decode("utf-16le").replace("\r\n", "\n").replace("\r", "\n")

    @property
    def rotation(self):
        return self.workspace.fpdf_get_page_rotation(self.page)


def fpdf_string(text):
    if text is not None:
        if isinstance(text, str):
            return text.encode("latin-1")
    return text


class Workspace:
    # pylint: disable=too-many-instance-attributes, too-many-statements
    def __init__(self):
        self.pdfium = None

    def load_library(self):
        assert self.pdfium is None, "Do not call this function more than once"

        script_dir = os.path.dirname(os.path.realpath(__file__))
        self.pdfium = cdll.LoadLibrary(os.path.join(script_dir, "libpdfium.so2"))

        self.init_config = FPDFLibraryConfig(2, c_void_p(), c_void_p(), 0)
        self.pdfium.FPDF_InitLibraryWithConfig(byref(self.init_config))
        self.pdfium.FPDF_GetLastError()

        # Load document
        prototype = CFUNCTYPE(c_void_p, c_char_p, c_char_p)
        self.fpdf_load_document = prototype(("FPDF_LoadDocument", self.pdfium))

        prototype = CFUNCTYPE(c_void_p, c_void_p, c_char_p)
        self.fpdf_load_custom_document = prototype(
            ("FPDF_LoadCustomDocument", self.pdfium)
        )

        prototype = CFUNCTYPE(None, c_void_p)
        self.fpdf_close_document = prototype(("FPDF_CloseDocument", self.pdfium))

        prototype = CFUNCTYPE(c_void_p, c_void_p, c_int)
        self.fpdf_load_page = prototype(("FPDF_LoadPage", self.pdfium))

        prototype = CFUNCTYPE(None, c_void_p)
        self.fpdf_close_page = prototype(("FPDF_ClosePage", self.pdfium))

        prototype = CFUNCTYPE(c_int, c_void_p)
        self.fpdf_get_page_count = prototype(("FPDF_GetPageCount", self.pdfium))

        prototype = CFUNCTYPE(c_double, c_void_p)
        self.fpdf_get_page_width = prototype(("FPDF_GetPageWidth", self.pdfium))

        prototype = CFUNCTYPE(c_double, c_void_p)
        self.fpdf_get_page_height = prototype(("FPDF_GetPageHeight", self.pdfium))

        prototype = CFUNCTYPE(c_int, c_void_p)
        self.fpdf_get_page_rotation = prototype(("FPDFPage_GetRotation", self.pdfium))

        prototype = CFUNCTYPE(POINTER(c_ubyte), c_int, c_int, c_int)
        self.fpdf_bitmap_create = prototype(("FPDFBitmap_Create", self.pdfium))

        prototype = CFUNCTYPE(None, c_void_p, c_int, c_int, c_int, c_int, c_ulong)
        self.fpdf_bitmap_fill_rect = prototype(("FPDFBitmap_FillRect", self.pdfium))

        prototype = CFUNCTYPE(
            None, c_void_p, c_void_p, c_int, c_int, c_int, c_int, c_int, c_int
        )
        self.fpdf_render_page_bitmap = prototype(("FPDF_RenderPageBitmap", self.pdfium))

        prototype = CFUNCTYPE(c_int, c_void_p)
        self.fpdf_bitmap_get_stride = prototype(("FPDFBitmap_GetStride", self.pdfium))

        prototype = CFUNCTYPE(POINTER(c_ubyte), c_void_p)
        self.fpdf_get_bitmap_buffer = prototype(("FPDFBitmap_GetBuffer", self.pdfium))

        prototype = CFUNCTYPE(None, c_void_p)
        self.fpdf_bitmap_destroy = prototype(("FPDFBitmap_Destroy", self.pdfium))

        # Text
        prototype = CFUNCTYPE(c_void_p, c_void_p)
        self.fpdf_text_load_page = prototype(("FPDFText_LoadPage", self.pdfium))

        prototype = CFUNCTYPE(None, c_void_p)
        self.fpdf_text_close_page = prototype(("FPDFText_ClosePage", self.pdfium))

        prototype = CFUNCTYPE(c_int, c_void_p)
        self.fpdf_text_count_chars = prototype(("FPDFText_CountChars", self.pdfium))

        prototype = CFUNCTYPE(c_int, c_void_p, c_int, c_int, c_ushort_p)
        self.fpdf_text_get_text = prototype(("FPDFText_GetText", self.pdfium))

        # PDF editing
        prototype = CFUNCTYPE(c_void_p)
        self.fpdf_create_new_document = prototype(
            ("FPDF_CreateNewDocument", self.pdfium)
        )

        prototype = CFUNCTYPE(c_void_p, c_void_p, c_int, c_double, c_double)
        self.fpdf_page_new = prototype(("FPDFPage_New", self.pdfium))

        prototype = CFUNCTYPE(None, c_void_p, c_void_p)
        self.fpdf_insert_object = prototype(("FPDFPage_InsertObject", self.pdfium))

        # Text object
        prototype = CFUNCTYPE(c_void_p, c_void_p, c_void_p, c_float)
        self.fpdf_page_obj_create_text_obj = prototype(
            ("FPDFPageObj_CreateTextObj", self.pdfium)
        )

        prototype = CFUNCTYPE(c_int, c_void_p, c_char_p)
        self.fpdf_text_set_text = prototype(("FPDFText_SetText", self.pdfium))

        # Image object
        prototype = CFUNCTYPE(c_void_p, c_void_p)
        self.fpdf_page_obj_new_image_obj = prototype(
            ("FPDFPageObj_NewImageObj", self.pdfium)
        )

        prototype = CFUNCTYPE(c_void_p, c_void_p, c_int, c_void_p, c_void_p)
        self.fpdf_image_obj_set_bitmap = prototype(
            ("FPDFImageObj_SetBitmap", self.pdfium)
        )

        # Transform
        prototype = CFUNCTYPE(
            c_int, c_void_p, c_float_p, c_float_p, c_float_p, c_float_p
        )
        self.fpdf_page_obj_get_bounds = prototype(
            ("FPDFPageObj_GetBounds", self.pdfium)
        )

        prototype = CFUNCTYPE(
            None, c_void_p, c_double, c_double, c_double, c_double, c_double, c_double
        )
        self.fpdf_page_obj_transform = prototype(("FPDFPageObj_Transform", self.pdfium))

        # Fonts
        prototype = CFUNCTYPE(c_void_p, c_void_p, c_uint8_p, c_uint32, c_int, c_int)
        self.fpdf_text_load_font = prototype(("FPDFText_LoadFont", self.pdfium))

        prototype = CFUNCTYPE(None, c_void_p)
        self.fpdf_font_close = prototype(("FPDFFont_Close", self.pdfium))

        # Fill
        prototype = CFUNCTYPE(c_int, c_void_p, c_int, c_int, c_int, c_int)
        self.fpdf_page_obj_set_fill_color = prototype(
            ("FPDFPageObj_SetFillColor", self.pdfium)
        )

        # Saving PDF
        prototype = CFUNCTYPE(c_int, c_void_p)
        self.fpdf_page_generate_content = prototype(
            ("FPDFPage_GenerateContent", self.pdfium)
        )

        prototype = CFUNCTYPE(c_int, c_void_p, c_void_p, c_ulong)
        self.fpdf_save_as_copy = prototype(("FPDF_SaveAsCopy", self.pdfium))

    def free_library(self):
        if self.pdfium is not None:
            self.pdfium.FPDF_DestroyLibrary()
            del self.pdfium
            self.pdfium = None

    def __enter__(self):
        self.load_library()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.free_library()

    def load_document(self, filename, password=None):
        result = self.fpdf_load_document(fpdf_string(filename), fpdf_string(password))
        if not result:
            error = self.pdfium.FPDF_GetLastError()
            assert False, f"ERROR {error}: unable to load '{filename}'"

        return Document(self, result)

    def load_document_custom(self, handler, password=None):
        file_reader = FPDFFileAccess(handler.size, handler.get_block, None)
        document = self.fpdf_load_custom_document(
            byref(file_reader), fpdf_string(password)
        )
        if not document:
            error = self.pdfium.FPDF_GetLastError()
            assert False, f"ERROR {error}: unable to load '{handler.filename}'"

        return Document(self, document)

    def new_document(self):
        doc = self.fpdf_create_new_document()
        return Document(self, doc)


class Handler:
    def __init__(self, file_obj, f_size, record=False, playback=False, cache=None):
        self.file_obj = file_obj
        self.size = f_size
        self.record = record
        self.playback = playback
        self.cache = {} if cache is None else cache

        @CFUNCTYPE(c_int, c_void_p, c_ulong, c_ubyte_p, c_ulong)
        def get_block(_param, position, p_buf, size):
            if self.playback and (position, size) in self.cache:
                data = cache[(position, size)]
            else:
                if self.playback:
                    print((position, size))
                # Seek in PDF file
                file_obj.seek(position, os.SEEK_SET)

                data = file_obj.read(size)

            if self.record:
                self.cache[(position, size)] = data

            # Copy over data
            ctypes.memmove(p_buf, c_char_p(data), size)
            return size

        self.get_block = get_block


class StorageHandler(Handler):
    def __init__(self, storage, filename, record=False, playback=False, cache=None):
        self.filename = filename
        self.handle = storage.open(filename, "rb").__enter__()
        size = storage.du(filename)[filename]
        super().__init__(self.handle, size, record, playback, cache)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.handle.close()


class FileHandler(Handler):
    def __init__(self, filename, record=False, playback=False, cache=None):
        self.filename = filename
        self.handle = open(filename, "rb")
        size = os.path.getsize(filename)
        super().__init__(self.handle, size, record, playback, cache)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.handle.close()


class GCSHandler(Handler):
    def __init__(self, fs, path, record=False, playback=False, cache=None):
        self.filename = path
        self.handle = fs.open(path, "rb")
        size = fs.du(path, total=True)
        super().__init__(self.handle, size, record, playback, cache)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.handle.close()
