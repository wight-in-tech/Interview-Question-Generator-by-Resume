import streamlit as st
import PyPDF2
import docx2txt
from pdfminer.high_level import extract_text
import tempfile
import os
import pdfplumber
import re
import google.generativeai as genai

def parse_questions(questions_text):
    """Parse the generated questions into a structured format"""
    sections = {}
    current_section = None
    current_questions = []
    
    for line in questions_text.split('\n'):
        line = line.strip()
        if line.endswith('Questions:'):
            if current_section and current_questions:
                sections[current_section] = current_questions
            current_section = line[:-1]  # Remove the colon
            current_questions = []
        elif line.startswith(tuple('1234567890')) and '. ' in line:
            question = line[line.find('.')+2:]  # Remove the number and dot
            current_questions.append(question)
    
    if current_section and current_questions:
        sections[current_section] = current_questions
        
    return sections

def get_interview_questions_gemini(resume_text):
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""Generate a list of interview questions based on the following resume information, focusing on the candidate's experience, skills, achievements, and education. The questions should assess the candidate's qualifications, problem-solving abilities, and relevant experiences:

        Instructions:
        1. Create exactly 5 technical questions based on the candidate's skills and experience
        2. Create exactly 5 behavioral questions relevant to their background
        3. Format the output with clear headers for each section
        4. Number each question
        5. Keep questions specific to their experience
        
        Resume:
        {resume_text}
        
        Please format the output as:
        
        Technical Questions:
        1. [Question]
        2. [Question]
        ...
        
        Behavioral Questions:
        1. [Question]
        2. [Question]
        ..."""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error with Gemini API: {str(e)}")
        return None

def get_feedback_for_answers(questions_and_answers):
    try:
        model = genai.GenerativeModel('gemini-pro')
        
        feedback_prompt = """Analyze the following interview answers and provide constructive feedback:
        
        For each answer, consider:
        1. Completeness of the response
        2. Relevance to the question
        3. Specific examples or details provided
        4. Areas for improvement
        
        Questions and Answers:
        """
        
        for q_type, qa_list in questions_and_answers.items():
            feedback_prompt += f"\n{q_type} Questions:\n"
            for i, (q, a) in enumerate(qa_list, 1):
                feedback_prompt += f"\nQ{i}: {q}\nAnswer: {a}\n"

        response = model.generate_content(feedback_prompt)
        return response.text
    except Exception as e:
        st.error(f"Error with Gemini API: {str(e)}")
        return None

def read_pdf_PyPDF2(file):
    """Read PDF using PyPDF2"""
    pdf_reader = PyPDF2.PdfReader(file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def read_pdf_pdfminer(file):
    """Read PDF using pdfminer"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        tmp_file.write(file.getvalue())
        tmp_file_path = tmp_file.name
    text = extract_text(tmp_file_path)
    os.unlink(tmp_file_path)
    return text

def read_pdf_pdfplumber(file):
    """Read PDF using pdfplumber"""
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def read_docx(file):
    """Read DOCX files"""
    text = docx2txt.process(file)
    return text

def process_text(text):
    """Process the extracted text"""
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def main():
    # Initialize session state
    if 'questions' not in st.session_state:
        st.session_state.questions = None
    if 'answers' not in st.session_state:
        st.session_state.answers = {}
    if 'feedback' not in st.session_state:
        st.session_state.feedback = None
    
    st.title("Resume Analyzer & Interview Question Generator 📄")
    
    # Add a sidebar
    st.sidebar.title("About")
    st.sidebar.info(
        "This application extracts text from resumes and generates tailored "
        "interview questions using Google's Gemini AI. Upload a resume to get started!"
    )
    
    # Check for API key
    if "GEMINI_API_KEY" not in st.secrets:
        st.error("""Please set the GEMINI_API_KEY in your Streamlit secrets.
                 You can get one from https://makersuite.google.com/app/apikey""")
        st.stop()
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload your resume (PDF or DOCX)", 
        type=["pdf", "docx"]
    )
    
    if uploaded_file is not None:
        file_details = {
            "Filename": uploaded_file.name,
            "File size": f"{uploaded_file.size / 1024:.0f} KB",
            "File type": uploaded_file.type
        }
        
        st.write("### File Details")
        st.json(file_details)
        
        # Add a spinner while processing
        with st.spinner("Processing document..."):
            try:
                if uploaded_file.type == "application/pdf":
                    text = read_pdf_pdfplumber(uploaded_file)
                    if not text.strip():
                        text = read_pdf_PyPDF2(uploaded_file)
                        if not text.strip():
                            text = read_pdf_pdfminer(uploaded_file)
                
                elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                    text = read_docx(uploaded_file)
                else:
                    st.error("Unsupported file format")
                    return
                
                # Process the extracted text
                processed_text = process_text(text)
                
                # Display extracted text
                st.write("### Extracted Text")
                with st.expander("Show extracted text"):
                    st.text_area("", processed_text, height=300)
                
                # Generate interview questions if not already generated
                if not st.session_state.questions:
                    st.write("### AI-Generated Interview Questions")
                    with st.spinner("Generating interview questions..."):
                        questions_text = get_interview_questions_gemini(processed_text)
                        if questions_text:
                            st.session_state.questions = parse_questions(questions_text)
                
                # Display questions and collect answers
                if st.session_state.questions:
                    st.write("### Interview Questions and Answers")
                    answers_provided = True
                    
                    for section, questions in st.session_state.questions.items():
                        st.write(f"\n#### {section}")
                        if section not in st.session_state.answers:
                            st.session_state.answers[section] = [""] * len(questions)
                            
                        for i, question in enumerate(questions):
                            st.write(f"\n**Q{i+1}:** {question}")
                            answer = st.text_area(
                                f"Your answer for {section} Q{i+1}",
                                st.session_state.answers[section][i],
                                key=f"{section}_answer_{i}",
                                height=100
                            )
                            st.session_state.answers[section][i] = answer
                            if not answer.strip():
                                answers_provided = False
                    
                    # Create a dictionary of questions and answers for feedback
                    questions_and_answers = {
                        section: list(zip(questions, st.session_state.answers[section]))
                        for section, questions in st.session_state.questions.items()
                    }
                    
                    # Generate feedback button
                    if answers_provided:
                        if st.button("Get AI Feedback on Answers"):
                            with st.spinner("Generating feedback..."):
                                feedback = get_feedback_for_answers(questions_and_answers)
                                if feedback:
                                    st.session_state.feedback = feedback
                    else:
                        st.warning("Please provide answers to all questions to get feedback.")
                    
                    # Display feedback if available
                    if st.session_state.feedback:
                        st.write("### AI Feedback")
                        st.markdown(st.session_state.feedback)
                        
                        # Add download buttons
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.download_button(
                                label="Download extracted text",
                                data=processed_text,
                                file_name=f"{uploaded_file.name}_extracted.txt",
                                mime="text/plain"
                            )
                        with col2:
                            questions_text = "\n\n".join([
                                f"{section}:\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
                                for section, questions in st.session_state.questions.items()
                            ])
                            st.download_button(
                                label="Download questions",
                                data=questions_text,
                                file_name=f"{uploaded_file.name}_questions.txt",
                                mime="text/plain"
                            )
                        with col3:
                            st.download_button(
                                label="Download feedback",
                                data=st.session_state.feedback,
                                file_name=f"{uploaded_file.name}_feedback.txt",
                                mime="text/plain"
                            )
                
                # Display text statistics
                st.write("### Text Statistics")
                stats = {
                    "Total characters": len(processed_text),
                    "Total words": len(processed_text.split()),
                    "Average word length": round(len(processed_text) / len(processed_text.split()), 2)
                }
                st.json(stats)
                
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")
                st.error("Please try uploading a different file or contact support.")

if __name__ == "__main__":
    main()