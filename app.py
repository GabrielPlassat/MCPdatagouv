import streamlit as st
import google.generativeai as genai
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import asyncio
import concurrent.futures

st.set_page_config(
    page_title="data.gouv.fr – Assistant IA",
    page_icon="🇫🇷",
    layout="wide"
)

st.title("🇫🇷 Assistant data.gouv.fr")
st.caption("Posez vos questions sur les jeux de données du portail open data français.")

DATAGOUV_MCP_URL = "https://mcp.data.gouv.fr/mcp"

api_key = st.secrets.get("GOOGLE_API_KEY", None)
if not api_key:
    st.error("⚠️ Clé API Google manquante. Ajoutez `GOOGLE_API_KEY` dans vos secrets Streamlit.")
    st.stop()

genai.configure(api_key=api_key)


async def query_with_mcp(question: str) -> str:
    async with streamablehttp_client(DATAGOUV_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()

            declarations = []
            for t in tools_result.tools:
                schema = dict(t.inputSchema)
                schema.pop("$schema", None)
                declarations.append(
                    genai.protos.FunctionDeclaration(
                        name=t.name,
                        description=t.description or "",
                        parameters=schema,
                    )
                )

            model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                tools=[genai.protos.Tool(function_declarations=declarations)],
                system_instruction=(
                    "Tu es un assistant expert en données publiques françaises. "
                    "Utilise les outils disponibles pour rechercher et analyser "
                    "les jeux de données de data.gouv.fr. "
                    "Réponds toujours en français, de façon claire et structurée. "
                    "Quand tu trouves des datasets, présente leur titre, organisation, "
                    "formats disponibles et date de mise à jour."
                ),
            )

            chat = model.start_chat()
            response = chat.send_message(question)

            # Boucle agentique
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
                        tool_result = await session.call_tool(fc.name, dict(fc.args))
                        result_text = "\n".join(
                            [c.text for c in tool_result.content if hasattr(c, "text")]
                        )
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
                return "Désolé, je n'ai pas pu obtenir une réponse."


def run_query(question: str) -> str:
    """Lance la coroutine dans un thread séparé avec son propre event loop
    pour éviter les conflits avec Streamlit."""
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(query_with_mcp(question))
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        return future.result(timeout=60)


# --- Sidebar ---
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

# --- Historique ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Input ---
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
