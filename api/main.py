from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import os
import fitz  # PyMuPDF
import io
import boto3
from openai import OpenAI
import json
import os

load_dotenv()

app = FastAPI()
openaiClient = OpenAI()
s3_client = boto3.client('s3')

aws_access_secret_key = os.getenv('AWS_ACCESS_KEY_ID') 
print(aws_access_secret_key)

# S3 bucket name
BUCKET_NAME = 'syncup-bucket-1'


def get_redaction_response(page_text, redaction_instructions):
    try:
        response = openaiClient.chat.completions.create(
            model="gpt-4-1106-preview",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful JSON-outputting redaction assistant. You output a JSON array with the exact strings and cited reasons (which may include spaces or weird characters) to redact from a PDF. "},
                {"role": "user", "content": 'Here is the PDF: ' + page_text + ' Redaction instructions:\n\n' + redaction_instructions + '\n\n Based only on the above instructions, do we need to redact anything from this document? If so, what? \n\n response format: {"overall_reasoning":"<Brief reasoning for redaction texts or not redacting anything>", "text_to_redact": [{"text":"<string 1>","reasoning":"<cited instruction from above>"}, {"text":"<string 2>","reasoning":"<cited instruction from above>"}]}'}
            ]
        )
        jsonResponse = json.loads(response.choices[0].message.content)
        return jsonResponse
    except Exception as e:
        print(f"Error: {e}")
        return None

def redact_pdf_and_upload(input_pdf_bytes, output_pdf_name, redact_instructions):
    print('Reading PDF')
    doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
    full_text = ''
    for page in doc:
        pageText = page.get_text()
        full_text += pageText

    print('Getting redactions from GPT4')
    redactionResponse = get_redaction_response(full_text, redact_instructions)
    if redactionResponse is None:
        print('Error getting strings to redact')
        return

    print('Redacting PDF')
    for page in doc:
        for textToRedact in redactionResponse['text_to_redact']:
            text_instances = page.search_for(textToRedact['text'])
            for inst in text_instances:
                redact = page.add_redact_annot(inst, text='')
                redact.update()

    for p in doc.pages():
        p.apply_redactions()

    # Save to a bytes buffer instead of a file
    print('Saving redacted PDF to buffer')
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    doc.close()


    # Upload to S3
    print('Uploading redacted PDF to S3')
    s3_client.upload_fileobj(buffer, BUCKET_NAME, output_pdf_name)

    # Generate a presigned URL for the S3 object
    print('Generating presigned URL')
    file_url = s3_client.generate_presigned_url('get_object',
                                            Params={'Bucket': BUCKET_NAME,
                                                    'Key': output_pdf_name},
                                            ExpiresIn=3600)  # URL expires in 1 hour

    print('file url:', file_url)
    buffer.close()
    return {"filename": output_pdf_name, 'file_url': file_url, 'redaction_response': redactionResponse}

@app.post("/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...), redact_instructions: str = Form(...)):
    input_pdf_bytes = await file.read()
    output_pdf_name = f"redacted_{file.filename}"

    result = redact_pdf_and_upload(input_pdf_bytes, output_pdf_name, redact_instructions)

    return {"filename": output_pdf_name, 'redaction_response': result['redaction_response'], 'file_url': result['file_url']}

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open('index.html', 'r') as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/download-pdf/{filename}")
async def download_pdf(filename: str):
    # Generate a presigned URL for the S3 object
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': BUCKET_NAME,
                                                            'Key': filename},
                                                    ExpiresIn=3600)  # Expires in 1 hour
        return {"url": response}
    except Exception as e:
        return {"error": f"Error generating URL: {str(e)}"}

@app.get("/test")
async def test():
    return {"message": "Hello, world!"}
