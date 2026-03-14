import zipfile
import lxml.etree as ET

namespaces = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
}

def extract_comments(docx_path):
    with zipfile.ZipFile(docx_path) as docx:
        try:
            comments_xml = docx.read('word/comments.xml')
            root = ET.fromstring(comments_xml)
            for comment in root.findall('.//w:comment', namespaces):
                c_id = comment.get(f"{{{namespaces['w']}}}id")
                author = comment.get(f"{{{namespaces['w']}}}author")
                text = ''.join(comment.itertext())
                print(f"Comment {c_id} by {author}: {text}")
        except Exception as e:
            print(f"Error: {e}")

extract_comments(r"E:\production\fillwise3.0\test.docx")
