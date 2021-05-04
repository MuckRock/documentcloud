from PyPDF2 import PdfFileWriter, PdfFileReader, PdfFileMerger

pdf_merger = PdfFileMerger()
pdf_merger.append("documentcloud/documents/processing/tests/pdfs/output_test6.pdf")
# pdf_merger.append("documentcloud/documents/processing/tests/pdfs/doc_3.pdf")
# pdf_merger.write("documentcloud/documents/processing/tests/pdfs/doc_merged.pdf")
