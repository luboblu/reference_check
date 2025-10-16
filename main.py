from flask import Flask, request, jsonify
from utils.parsers import extract_paragraphs_from_pdf, extract_paragraphs_from_docx
from utils.extractors import extract_reference_section_improved, clip_until_stop, post_process_pdf_references
from utils.style_detector import detect_reference_style, merge_references_by_heads, is_reference_head
from utils.searchers import search_scholar_by_title, search_scholar_by_ref_text, search_scopus_by_title, search_crossref_by_doi
from utils.text_cleaner import clean_title, clean_title_for_remedial
from config.keys import SERPAPI_KEY, SCOPUS_KEY
from datetime import datetime
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route("/verify", methods=["POST"])
def verify_reference():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = file.filename.lower()
    if filename.endswith(".pdf"):
        paragraphs = extract_paragraphs_from_pdf(file)
    elif filename.endswith(".docx"):
        paragraphs = extract_paragraphs_from_docx(file)
    else:
        return jsonify({"error": "Unsupported file type"}), 400

    refs, heading, method = extract_reference_section_improved(paragraphs)

    if not refs:
        return jsonify({
            "reference_count": 0,
            "heading": heading,
            "method": method,
            "results": [],
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    if filename.endswith(".pdf"):
        refs = post_process_pdf_references(refs)

    results = []
    scholar_logs = []
    for ref in refs:
        style = detect_reference_style(ref)
        doi = search_crossref_by_doi(ref, only_check=True)
        crossref = None
        if doi == "found":
            crossref = "found"
        elif doi == "no_doi":
            crossref = "no_doi"
        else:
            crossref = doi

        cleaned = clean_title(ref)
        scopus = search_scopus_by_title(cleaned, SCOPUS_KEY)
        gs_url, gs_type = search_scholar_by_title(cleaned, SERPAPI_KEY)
        scholar_logs.append(f"{gs_type}: {cleaned}")

        remedial_url = None
        if gs_type == "no_result":
            remedial_url, remedial_type = search_scholar_by_ref_text(ref, SERPAPI_KEY)
            if remedial_type == "remedial":
                scholar_hits_type = "remedial"
            else:
                scholar_hits_type = "no_result"
        else:
            scholar_hits_type = gs_type

        results.append({
            "original": ref,
            "cleaned": cleaned,
            "style": style,
            "crossref": crossref,
            "scopus": scopus,
            "scholar_type": scholar_hits_type,
            "scholar_url": gs_url if gs_url else remedial_url
        })

    return jsonify({
        "reference_count": len(results),
        "heading": heading,
        "method": method,
        "results": results,
        "scholar_logs": scholar_logs,
        "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

def main(request):
    with app.app_context():
        return app.full_dispatch_request()
