from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, HTMLResponse
import os
import fitz  # PyMuPDF
import shutil

app = FastAPI()

# Directory where files will be saved
FILE_DIR = "uploaded_files"
if not os.path.exists(FILE_DIR):
    os.makedirs(FILE_DIR)

def redact_pdf(input_pdf, output_pdf, word_to_redact):
    doc = fitz.open(input_pdf)

    # Iterate through each page
    for page in doc:
      # fitz.TEXT_INHIBIT_SPACES
      # search default flags (TEXT_PRESERVE_LIGATURES | TEXT_PRESERVE_WHITESPACE | TEXT_MEDIABOX_CLIP | TEXT_DEHYPHENATE)
      flags = (fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_INHIBIT_SPACES | fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP | fitz.TEXT_DEHYPHENATE)
      textPage = page.get_textpage(flags=flags)
      pageText = page.get_text("words", flags=flags)
      concatenatedText = ' '.join(list(map(lambda x: x[4], pageText)))

      #print(pageText)
      text_instances = page.search_for(word_to_redact, flags=flags)
      #combined = combineNearbyRects(text_instances)
      #combined = [fitz.Rect(254.8533172607422, 475.08038330078125, 295.45037841796875, 484.93927001953125)]
      
      #print('string match occurances', len(re.findall(word_to_redact.lower(), pageText.lower())))
      print('search_for instances', len(text_instances))
      #print('combined instances', len(combined))


      # Iterate through each found instance and create a redaction annotation
      for inst in text_instances:
        #print(inst)
        redact = page.add_redact_annot(inst, text='', fill=(0,0,0)) # .join(['X' for l in redact_word]))  # Replace text with a blank space
        redact.update()

    # # Apply the redactions
    for p in doc.pages():
        p.apply_redactions()
    #doc.apply_redactions()

    # Save the redacted document
    doc.save(output_pdf)
    doc.close()

# Serve the static HTML file
@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open('index.html', 'r') as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.post("/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...), redact_instructions: str = Form(...)):
    input_pdf_path = os.path.join(FILE_DIR, f"temp_{file.filename}")
    output_pdf_path = os.path.join(FILE_DIR, f"redacted_{file.filename}")

    print('redact_instructions',redact_instructions)

    with open(input_pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    redact_pdf(input_pdf_path, output_pdf_path, redact_instructions)

    os.remove(input_pdf_path)  # Remove the original file
    
    returnValue = {"filename": f"redacted_{file.filename}"}

    return returnValue

@app.get("/download-pdf/{filename}")
async def download_pdf(filename: str):
    print('got request for file wtih name', filename)
    file_path = os.path.join(FILE_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='application/pdf')
    return {"error": "File not found"}
