import zipfile
import lxml.etree as ET

namespaces = {
    'ap': 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'
}

def get_page_count(docx_path):
    with zipfile.ZipFile(docx_path) as docx:
        try:
            app_xml = docx.read('docProps/app.xml')
            root = ET.fromstring(app_xml)
            pages = root.find('.//ap:Pages', namespaces)
            if pages is not None:
                print(f"Pages: {pages.text}")
        except Exception as e:
            print(f"Error: {e}")

get_page_count(r"E:\production\fillwise3.0\test.docx")
