import streamlit as st
import google.generativeai as genai
import requests
import json

st.set_page_config(
    page_title="data.gouv.fr – Assistant IA",
    page_icon="🇫🇷",
    layout="wide"
)

st.title("🇫🇷 Assistant data.gouv.fr")
st.caption("Posez vos questions sur les jeux de données du portail open data français.")

api_key = st.secrets.get("GOOGLE_API_KEY", None)
if not api_key:
    st.error("⚠️ Clé API Google manquante. Ajoutez `GOOGLE_API_KEY` dans vos secrets Streamlit.")
    st.stop()

genai.configure(api_key=api_key)

MCP_URL = "https://mcp.data.gouv.fr/mcp"

# ─── Client MCP minimal en JSON-RPC synchrone ────────────────────────────────

class MCPClient:
    """Client MCP Streamable HTTP sans librairie async."""

    def __init__(self, url: str):
        self.url = url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        self._id = 0
        self._mcp_session_id = None
        self._initialized = False

    def _next_id(self):
        self._id += 1
        return self._id

    def _post(self, payload: dict) -> dict:
        headers = {}
        if self._mcp_session_id:
            headers["Mcp-Session-Id"] = self._mcp_session_id

        resp = self.session.post(self.url, json=payload, headers=headers, timeout=30)

        # Récupérer le session ID si fourni
        if "Mcp-Session-Id" in resp.headers:
            self._mcp_session_id = resp.headers["Mcp-Session-Id"]

        content_type = resp.headers.get("Content-Type", "")

        # Réponse SSE : extraire le JSON de chaque ligne "data: ..."
        if "text/event-stream" in content_type:
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str and data_str != "[DONE]":
                        try:
                            return json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
            return {}

        # Réponse JSON directe
        if resp.status_code == 202:
            return {}  # Accepted, pas de corps

        return resp.json()

    def initialize(self):
        if self._initialized:
            return
        payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": self._next_id(),
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "streamlit-poc", "version": "1.0"},
            },
        }
        self._post(payload)
        # Envoyer initialized
        self._post({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        self._initialized = True

    def list_tools(self) -> list:
        self.initialize()
        result = self._post({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": self._next_id(),
            "params": {},
        })
        return result.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        self.initialize()
        result = self._post({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": self._next_id(),
            "params": {"name": name, "arguments": arguments},
        })
        content = result.get("result", {}).get("content", [])
        return "\n".join(
            c.get("text", "") for c in content if c.get("type") == "text"
        )


@st.cache_resource
def get_mcp_client():
    return MCPClient(MCP_URL)


def get_tool_declarations():
    return [
        genai.protos.FunctionDeclaration(
            name="search_datasets",
            description="Recherche des jeux de données sur data.gouv.fr par mots-clés.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Mots-clés de recherche"},
                    "page_size": {"type": "integer", "description": "Nombre de résultats (max 20)"},
                },
                "required": ["query"],
            },
        ),
        genai.protos.FunctionDeclaration(
            name="get_dataset_info",
            description="Informations détaillées sur un dataset à partir de son ID.",
            parameters={
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string", "description": "ID du dataset"},
                },
                "required": ["dataset_id"],
            },
        ),
        genai.protos.FunctionDeclaration(
            name="list_dataset_resources",
            description="Liste les fichiers disponibles dans un dataset.",
            parameters={
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string", "description": "ID du dataset"},
                },
                "required": ["dataset_id"],
            },
        ),
        genai.protos.FunctionDeclaration(
            name="query_resource_data",
            description="Récupère les données tabulaires d'une ressource CSV/XLS.",
            parameters={
                "type": "object",
                "properties": {
                    "resource_id": {"type": "string", "description": "ID de la ressource"},
                    "page": {"type": "integer", "description": "Numéro de page"},
                },
                "required": ["resource_id"],
            },
        ),
    ]


# ─── Boucle agentique Gemini ─────────────────────────────────────────────────

def run_query(question: str) -> str:
    client = get_mcp_client()
    declarations = get_tool_declarations()

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        tools=[genai.protos.Tool(function_declarations=declarations)],
        system_instruction=(
            "Tu es un assistant expert en données publiques françaises. "
            "Utilise les outils MCP disponibles pour rechercher et analyser "
            "les jeux de données de data.gouv.fr. "
            "Réponds toujours en français, de façon claire et structurée. "
            "Quand tu trouves des datasets, présente leur titre, organisation, "
            "formats disponibles et date de mise à jour."
        ),
    )

    chat = model.start_chat()
    response = chat.send_message(question)

    for _ in range(10):
        func_calls = []
        try:
            for part in response.candidates[0].content.parts:
                if part.function_call and part.function_call.name:
                    func_calls.append(part.function_call)
        except Exception:
            break

        if not func_calls:
            break

        tool_responses = []
        for fc in func_calls:
            try:
                result_text = client.call_tool(fc.name, dict(fc.args))
            except Exception as e:
                result_text = f"Erreur outil {fc.name}: {e}"

            tool_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=fc.name,
                        response={"result": result_text},
                    )
                )
            )

        response = chat.send_message(
            genai.protos.Content(parts=tool_responses)
        )

    try:
        return response.text
    except Exception:
        return "Désolé, je n'ai pas pu obtenir de réponse."


# ─── Interface ────────────────────────────────────────────────────────────────

st.sidebar.header("💡 Exemples de questions")
examples = [
    "Quels jeux de données sont disponibles sur les prix de l'immobilier ?",
    "Trouve des données sur la population des communes françaises",
    "Quels datasets parlent de la qualité de l'air ?",
    "Montre-moi les données sur les accidents de la route",
    "Y a-t-il des données sur les résultats des élections ?",
]
for ex in examples:
    if st.sidebar.button(ex, use_container_width=True):
        st.session_state["question"] = ex

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

default_q = st.session_state.pop("question", "")
question = st.chat_input("Posez votre question sur les données publiques françaises...")

if not question and default_q:
    question = default_q

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Recherche en cours sur data.gouv.fr..."):
            try:
                answer = run_query(question)
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error(f"Erreur : {e}")

if st.session_state.messages:
    if st.sidebar.button("🗑️ Nouvelle conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
