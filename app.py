import streamlit as st
import pandas as pd
import numpy as np
import pickle
import re
import nltk
from nltk.tokenize import sent_tokenize
import time
import matplotlib.pyplot as plt
import seaborn as sns

# Set page configuration
st.set_page_config(
    page_title="Text Summarizer",
    page_icon="📝",
    layout="wide"
)

# Download NLTK resources
nltk.download('punkt', quiet=True)

# Load models
@st.cache_resource
def load_domain_model():
    try:
        with open('fast_rf_classifier.pkl', 'rb') as f:
            model = pickle.load(f)
        return model
    except Exception as e:
        st.error(f"Error loading domain model: {e}")
        # Create a simple placeholder
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(n_estimators=10, random_state=42)

# Extract features for sentence importance classification
def extract_sentence_features(sentence, article_sentences, position, article_text):
    """Extract features that may indicate sentence importance"""
    # Basic position and length features
    features = {
        'position': position,  # Position in document
        'position_norm': position / len(article_sentences),  # Normalized position
        'length': len(sentence.split()),  # Sentence length
        'length_norm': min(len(sentence.split()) / 30, 1.0),  # Normalized length capped at 30 words
    }
    
    # News-specific features
    features.update({
        'contains_number': 1 if bool(re.search(r'\d', sentence)) else 0,  # Contains numbers
        'starts_with_quote': 1 if sentence.strip().startswith('"') else 0,  # Starts with quote
        'contains_named_entity': 1 if bool(re.search(r'[A-Z][a-z]+', sentence)) else 0,  # Contains capitalized words
        'first_sentence': 1 if position == 0 else 0,  # Is the first sentence
        'second_sentence': 1 if position == 1 else 0,  # Is the second sentence
        'early_paragraph': 1 if position < 5 else 0,  # Is in early paragraphs
    })
    
    # Content features
    important_words = ['announced', 'revealed', 'discovered', 'said', 'reported', 'according', 
                       'important', 'significant', 'crucial', 'critical', 'key', 'major']
    features['important_word_count'] = sum(1 for word in sentence.lower().split() 
                                          if word in important_words)
    
    # Sentence starts with a pronoun (less likely to be standalone important)
    pronouns = ['he', 'she', 'it', 'they', 'we', 'this', 'that', 'these', 'those']
    first_word = sentence.split()[0].lower() if sentence.split() else ""
    features['starts_with_pronoun'] = 1 if first_word in pronouns else 0
    
    return features

# Function to summarize text using domain model
def domain_tuned_summarize(article_text, classifier, num_sentences=3):
    """Use the trained classifier to select important sentences"""
    # Tokenize into sentences
    sentences = sent_tokenize(article_text)
    
    # Filter out very short sentences
    valid_sentences = []
    valid_indices = []
    for i, s in enumerate(sentences):
        if isinstance(s, str) and len(s.strip()) > 5:
            valid_sentences.append(s)
            valid_indices.append(i)
    
    # Handle short articles
    if len(valid_sentences) <= num_sentences:
        return valid_sentences, list(range(len(valid_sentences))), None, None
    
    # Extract features
    features = []
    for i, sentence in enumerate(valid_sentences):
        features.append(extract_sentence_features(sentence, valid_sentences, i, article_text))
    
    features_df = pd.DataFrame(features)
    
    try:
        # Predict importance
        importance_scores = classifier.predict_proba(features_df)[:, 1]  # Probability of class 1
        
        # Get feature importances for explainability
        feature_importances = None
        if hasattr(classifier, 'feature_importances_'):
            feature_importances = dict(zip(features_df.columns, classifier.feature_importances_))
    except Exception as e:
        st.warning(f"Error in prediction: {e}. Using fallback method.")
        # Simple fallback based on position
        importance_scores = [(len(valid_sentences) - i) / len(valid_sentences) for i in range(len(valid_sentences))]
        feature_importances = None
    
    # Rank sentences
    ranked_sentences = sorted(
        [(importance_scores[i], i, s) for i, s in enumerate(valid_sentences)],
        reverse=True
    )
    
    # Select top sentences based on importance
    selected_indices = [item[1] for item in ranked_sentences[:num_sentences]]
    
    # Get original indices (for highlighting in the UI)
    original_indices = [valid_indices[i] for i in selected_indices]
    
    # Sort by position for readability
    sorted_pairs = sorted(zip(selected_indices, original_indices))
    selected_indices = [pair[0] for pair in sorted_pairs]
    original_indices = [pair[1] for pair in sorted_pairs]
    
    summary = [valid_sentences[i] for i in selected_indices]
    
    # Create explainability data - features for each selected sentence
    sentence_explanations = []
    for idx in selected_indices:
        feature_dict = features_df.iloc[idx].to_dict()
        sentence_explanations.append({
            'sentence': valid_sentences[idx],
            'features': feature_dict,
            'importance_score': importance_scores[idx]
        })
    
    return summary, original_indices, sentence_explanations, feature_importances

# Function to create explainability visualization
def create_feature_importance_chart(feature_importances):
    if not feature_importances:
        return None
    
    # Convert to dataframe and sort
    importance_df = pd.DataFrame({
        'Feature': list(feature_importances.keys()),
        'Importance': list(feature_importances.values())
    }).sort_values('Importance', ascending=False)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(x='Importance', y='Feature', data=importance_df, ax=ax)
    ax.set_title('Feature Importance for Sentence Selection')
    ax.set_xlabel('Relative Importance')
    ax.set_ylabel('Feature')
    
    return fig

# Function to display feature values for a sentence with explanation
def display_sentence_features(sentence_data, feature_importances):
    st.subheader(f"Why this sentence was selected:")
    
    # Display the sentence
    st.markdown(f"**\"{sentence_data['sentence']}\"**")
    st.write(f"Overall importance score: {sentence_data['importance_score']:.2f}")
    
    # Sort features by importance
    if feature_importances:
        sorted_features = sorted(
            sentence_data['features'].items(), 
            key=lambda x: feature_importances.get(x[0], 0), 
            reverse=True
        )
    else:
        sorted_features = sorted(
            sentence_data['features'].items(), 
            key=lambda x: x[1], 
            reverse=True
        )
    
    # Create a more user-friendly display
    feature_display = {
        'position': "Position in the document",
        'position_norm': "Normalized position (0 = start, 1 = end)",
        'length': "Number of words",
        'length_norm': "Normalized length (capped at 30 words)",
        'contains_number': "Contains numbers",
        'starts_with_quote': "Starts with a quote",
        'contains_named_entity': "Contains named entities (capitalized words)",
        'first_sentence': "Is the first sentence",
        'second_sentence': "Is the second sentence",
        'early_paragraph': "Appears in early paragraphs",
        'important_word_count': "Number of important words",
        'starts_with_pronoun': "Starts with a pronoun"
    }
    
    # Display top features with explanations
    for feature_name, value in sorted_features:
        importance = feature_importances.get(feature_name, 0) if feature_importances else 0
        display_name = feature_display.get(feature_name, feature_name)
        
        # For binary features, convert to Yes/No
        if value in [0, 1] and feature_name not in ['position', 'important_word_count', 'length']:
            display_value = "Yes" if value == 1 else "No"
        else:
            display_value = f"{value:.2f}" if isinstance(value, float) else value
        
        if importance > 0.01:  # Only show somewhat important features
            st.write(f"**{display_name}**: {display_value} *(Importance: {importance:.3f})*")
        else:
            st.write(f"**{display_name}**: {display_value}")
    
# Main app
def main():
    st.title("ExplainaSumm")
    st.markdown("""
    This app uses a domain-specific machine learning model to summarize text and explains why certain sentences were selected.
    Simply paste your text below and adjust the number of sentences you want in your summary.
    """)
    
    # Load the models
    domain_model = load_domain_model()
    
    # Sidebar options
    st.sidebar.title("Summarization Options")
    
    num_sentences = st.sidebar.slider(
        "Number of sentences in summary:",
        min_value=1,
        max_value=10,
        value=3,
        help="Select how many sentences you want in your summary"
    )
    
    show_stats = st.sidebar.checkbox("Show sentence statistics", value=False)
    highlight_sentences = st.sidebar.checkbox("Highlight selected sentences in original text", value=True)
    show_explanation = st.sidebar.checkbox("Show why sentences were selected", value=True)
    
    # Input for article text
    article_text = st.text_area("Paste your text here:", 
                               height=300, 
                               placeholder="Paste the article or text you want to summarize...")
    
    # Process the text when submitted
    if st.button("Summarize"):
        if not article_text:
            st.warning("Please paste some text to summarize.")
            return
            
        with st.spinner("Generating summary..."):
            # Track summarization time
            start_time = time.time()
            
            # Get the summary
            try:
                summary_sentences, selected_indices, sentence_explanations, feature_importances = domain_tuned_summarize(
                    article_text, domain_model, num_sentences=num_sentences
                )
            except Exception as e:
                st.error(f"Error generating summary: {e}")
                st.stop()
            
            # Calculate time taken
            time_taken = time.time() - start_time
            
            # Display stats
            st.success(f"Summary generated in {time_taken:.2f} seconds!")
            
            # Display the summary
            st.subheader("Summary")
            st.markdown(f"<div style='background-color:#f0f2f6; padding:15px; border-radius:5px'>{' '.join(summary_sentences)}</div>", unsafe_allow_html=True)
            
            if show_stats:
                st.subheader("Statistics")
                col1, col2, col3 = st.columns(3)
                
                original_word_count = len(article_text.split())
                summary_word_count = sum(len(s.split()) for s in summary_sentences)
                
                col1.metric("Original word count", original_word_count)
                col2.metric("Summary word count", summary_word_count)
                col3.metric("Compression ratio", f"{summary_word_count/original_word_count:.1%}")
            
            # Show explainability information
            if show_explanation and feature_importances:
                st.subheader("How the Model Works")
                st.write("This summarizer uses a machine learning model to identify important sentences. Here's what the model considers important:")
                
                # Display feature importance chart
                importance_chart = create_feature_importance_chart(feature_importances)
                if importance_chart:
                    st.pyplot(importance_chart)
                
                # Show detailed explanation for each selected sentence
                st.subheader("Why These Sentences Were Selected")
                if sentence_explanations:
                    for i, sent_data in enumerate(sentence_explanations):
                        with st.expander(f"Sentence {i+1}"):
                            display_sentence_features(sent_data, feature_importances)
            
            # Show original text with highlighted sentences
            if highlight_sentences:
                st.subheader("Original Text with Highlighted Sentences")
                
                # Split the original text into sentences for highlighting
                all_sentences = sent_tokenize(article_text)
                
                # Create highlighted HTML
                highlighted_text = ""
                for i, sentence in enumerate(all_sentences):
                    if i in selected_indices:
                        highlighted_text += f"<mark style='background-color: #FFFF00'>{sentence}</mark> "
                    else:
                        highlighted_text += f"{sentence} "
                
                st.markdown(f"<div style='background-color:#f0f2f6; padding:15px; border-radius:5px'>{highlighted_text}</div>", 
                          unsafe_allow_html=True)

# Run the app
if __name__ == "__main__":
    main()