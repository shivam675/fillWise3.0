import zipfile
import lxml.etree as ET
from docx import Document

namespaces = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
}

def extract_linked_comments(docx_path):
    comments_dict = {}
    with zipfile.ZipFile(docx_path) as docx:
        try:
            comments_xml = docx.read('word/comments.xml')
            root = ET.fromstring(comments_xml)
            for comment in root.findall('.//w:comment', namespaces):
                c_id = comment.get(f"{{{namespaces['w']}}}id")
                author = comment.get(f"{{{namespaces['w']}}}author")
                text = "".join(comment.itertext())
                comments_dict[c_id] = {'author': author, 'text': text}
        except KeyError:
            pass

    doc = Document(docx_path)
    for p in doc.paragraphs:
        # Search for w:commentRangeStart in the lxml element
        xml_str = ET.tostring(p._element)
        c_refs = p._element.xpath('.//w:commentRangeStart/@w:id')
        if c_refs:
            print(f"Para: {p.text[:50]}...")
            for c_id in set(c_refs):
                c = comments_dict.get(str(c_id))
                if c:
                    print(f"  -> Comment: {c['text']}")

extract_linked_comments(r"E:\production\fillwise3.0\test.docx")
