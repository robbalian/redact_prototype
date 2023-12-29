from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, HTMLResponse
from dotenv import load_dotenv
import os
import fitz  # PyMuPDF
import shutil
from openai import OpenAI
import json

load_dotenv()

app = FastAPI()
openaiClient = OpenAI()

# Directory where files will be saved
FILE_DIR = "uploaded_files"
if not os.path.exists(FILE_DIR):
    os.makedirs(FILE_DIR)

def get_redaction_strings(page_text, redaction_instructions):
  try:
      response = openaiClient.chat.completions.create(
          model= "gpt-4-1106-preview", #"gpt-4-1106-preview", #"gpt-3.5-turbo-1106"
          response_format={ "type": "json_object" },
          messages=[
              {"role": "system", "content": "You are a helpful JSON-outputting redaction assistant. You output a JSON array with the exact strings (which may include spaces or weird characters) to redact from a PDF. "},
              {"role": "user", "content": 'Please identify the strings to redact based on these instructions: ' + redaction_instructions + \
               '\n Note: ONLY make these redactions. It\'s very important to not OVER-redact information. \
                You should NOT redact information that should be public (the clerks office, the attorneys trying the case, the recipient of the letter)\
                \n\n Here is the text: '+page_text+' \n\n reponse format: {"strings_to_redact": ["string1", "string2"]}'}
          ]
      )
      print(response)
      jsonResponse = json.loads(response.choices[0].message.content)
      return jsonResponse['strings_to_redact']  # Adjust according to the expected format
  except Exception as e:
      print(f"Error: {e}")
      return None

def redact_pdf(input_pdf, output_pdf, redact_instructions):
    doc = fitz.open(input_pdf)



    # Iterate through each page
    full_text = ''
    for page in doc:
      # fitz.TEXT_INHIBIT_SPACES
      # search default flags (TEXT_PRESERVE_LIGATURES | TEXT_PRESERVE_WHITESPACE | TEXT_MEDIABOX_CLIP | TEXT_DEHYPHENATE)
      flags = (fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_INHIBIT_SPACES | fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP | fitz.TEXT_DEHYPHENATE)
      pageText = page.get_text("text", flags=flags)
      full_text += pageText


    stringsToRedact = get_redaction_strings(full_text, redact_instructions)      
    print('stringsToRedact', stringsToRedact)

    if stringsToRedact is None:
      print('error getting strings to redact')
      return



    # Iterate through each page
    for page in doc:
      # fitz.TEXT_INHIBIT_SPACES
      # search default flags (TEXT_PRESERVE_LIGATURES | TEXT_PRESERVE_WHITESPACE | TEXT_MEDIABOX_CLIP | TEXT_DEHYPHENATE)
      flags = (fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_INHIBIT_SPACES | fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP | fitz.TEXT_DEHYPHENATE)
      textPage = page.get_textpage(flags=flags)
      pageText = page.get_text("text", flags=flags)

      for stringToRedact in stringsToRedact:
        text_instances = page.search_for(stringToRedact, flags=flags, textpage=textPage)
        print(text_instances)
        print(f'redacting {stringToRedact} with {len(text_instances)} instances')

        # Iterate through each found instance and create a redaction annotation
        for inst in text_instances:
          #print(inst)
          redact = page.add_redact_annot(inst, text='', fill=(0,0,0)) # .join(['X' for l in redact_word]))  # Replace text with a blank space
          redact.update()

    # # Apply the redactions
    for p in doc.pages():
        p.apply_redactions()

    # Save the redacted document
    doc.save(output_pdf)
    doc.close()
    return {"filename": output_pdf, 'redacted_strings': stringsToRedact}

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

    result = redact_pdf(input_pdf_path, output_pdf_path, redact_instructions)

    os.remove(input_pdf_path)  # Remove the original file
    
    returnValue = {"filename": f"redacted_{file.filename}", 'redacted_strings': result['redacted_strings']}

    return returnValue

@app.get("/download-pdf/{filename}")
async def download_pdf(filename: str):
    print('got request for file wtih name', filename)
    file_path = os.path.join(FILE_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='application/pdf')
    return {"error": "File not found"}
