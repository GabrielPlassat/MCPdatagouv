import streamlit as st
import anthropic

st.set_page_config(
    page_title="data.gouv.fr – Assistant IA",
    page_icon="🇫🇷",
    layout="wide"
)

st.title("🇫🇷 Assistant data.gouv.fr")
st.caption("Posez vos questions sur les jeux de données du portail open data français.")

# --- Configuration ---
DATAGOUV_MCP_URL = "https://mcp.data.gouv.fr/mcp"

# Clé API depuis les secrets Streamlit
api_key = st.secrets.get("ANTHROPIC_API_KEY", None)
if not api_key:
    st.error("⚠️ Clé API Anthropic manquante. Ajoutez `ANTHROPIC_API_KEY` dans vos secrets Streamlit.")
    st.stop()

client = anthropic.Anthropic(api_key=api_key)

# --- Exemples de questions ---
st.sidebar.header("💡 Exemples de questions")
examples = [
    "Quels jeux de données sont disponibles sur les prix de l'immobilier ?",
    "Trouve des données sur la population des communes françaises",
    "Quels datasets parlent de la qualité de l'air ?",
    "Montre-moi les données sur les accidents de la route en 2023",
    "Y a-t-il des données sur les résultats des élections présidentielles ?",
]
for ex in examples:
    if st.sidebar.button(ex, use_container_width=True):
        st.session_state["question"] = ex

# --- Historique de conversation ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Affichage de l'historique
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Input utilisateur ---
default_q = st.session_state.pop("question", "")
question = st.chat_input("Posez votre question sur les données publiques françaises...")

# Si un exemple a été cliqué, on l'utilise comme question
if not question and default_q:
    question = default_q

if question:
    # Afficher la question
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Appel à l'API Anthropic avec le MCP data.gouv.fr
    with st.chat_message("assistant"):
        with st.spinner("Recherche en cours sur data.gouv.fr..."):
            try:
                # Construction de l'historique pour l'API
                api_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ]

                response = client.beta.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=4096,
                    system=(
                        "Tu es un assistant expert en données publiques françaises. "
                        "Tu utilises le MCP data.gouv.fr pour rechercher et analyser "
                        "des jeux de données officiels. Réponds en français, de façon "
                        "claire et structurée. Quand tu trouves des datasets pertinents, "
                        "présente-les avec leurs caractéristiques principales (titre, "
                        "organisation productrice, formats disponibles, date de mise à jour)."
                    ),
                    messages=api_messages,
                    mcp_servers=[
                        {
                            "type": "url",
                            "url": DATAGOUV_MCP_URL,
                            "name": "datagouv",
                        }
                    ],
                    betas=["mcp-client-2025-04-04"],
                )

                # Extraire la réponse texte
                answer = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        answer += block.text

                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})

            except anthropic.APIError as e:
                st.error(f"Erreur API Anthropic : {e}")
            except Exception as e:
                st.error(f"Erreur inattendue : {e}")

# Bouton pour réinitialiser la conversation
if st.session_state.messages:
    if st.sidebar.button("🗑️ Nouvelle conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
