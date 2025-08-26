from flask import Flask, request, redirect, render_template_string, jsonify
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_FOLDER = './uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Make sure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# HTML template for file upload page with progress
UPLOAD_HTML = """
<!doctype html>
<html>
<head>
    <title>Upload a File</title>
</head>
<body>
    <h1>Upload a File</h1>
    <form id="uploadForm" method="post" enctype="multipart/form-data">
        <input type="file" name="file" id="file">
        <input type="submit" value="Upload">
    </form>
    <progress id="progressBar" value="0" max="100" style="width:300px;"></progress>
    <p id="status"></p>
    <p id="loaded_n_total"></p>

    <script>
        document.getElementById("uploadForm").onsubmit = function(event) {
            event.preventDefault();
            var file = document.getElementById("file").files[0];
            var formData = new FormData();
            formData.append("file", file);

            var ajax = new XMLHttpRequest();
            ajax.upload.addEventListener("progress", progressHandler, false);
            ajax.addEventListener("load", completeHandler, false);
            ajax.addEventListener("error", errorHandler, false);
            ajax.addEventListener("abort", abortHandler, false);
            ajax.open("POST", "/upload");
            ajax.send(formData);
        }

        function progressHandler(event) {
            document.getElementById("loaded_n_total").innerHTML = "Uploaded " + event.loaded + " bytes of " + event.total;
            var percent = (event.loaded / event.total) * 100;
            document.getElementById("progressBar").value = Math.round(percent);
            document.getElementById("status").innerHTML = Math.round(percent) + "% uploaded... please wait";
        }

        function completeHandler(event) {
            document.getElementById("status").innerHTML = event.target.responseText;
            document.getElementById("progressBar").value = 0;
        }

        function errorHandler(event) {
            document.getElementById("status").innerHTML = "Upload Failed";
        }

        function abortHandler(event) {
            document.getElementById("status").innerHTML = "Upload Aborted";
        }
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    return render_template_string(UPLOAD_HTML)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return f'File uploaded successfully: {filename}'

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)