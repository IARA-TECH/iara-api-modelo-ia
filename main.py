from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
import google.generativeai as genai
from dotenv import load_dotenv
import os
import PIL.Image
import io
import pandas as pd
from tempfile import NamedTemporaryFile
import asyncio
from scheduler.routes.health_router import router as health_router
from scheduler.keep_alive import keep_alive
from contextlib import asynccontextmanager

# === CONFIGURAÇÃO ===
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ Erro: GEMINI_API_KEY não encontrada no arquivo .env")

genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.5-flash")

# === PROMPT FIXO ===
PROMPT_FIXO = """
Sua função é contar por linha os valores para condena parcial e condena total de cada problema em uma indústria aviária.

Para cada tipo de condena (parcial e total), exitem 3 colunas para realizar a contagem CENTENA (amarelo), DEZENA (azul) e UNIDADE (vermelho), assim você irá realizar a soma, se mexer x vermelhas e y amarela = x*1 + y*10 
Cada linha representa uma categoria, informada ao meio da imagem

### REGRA PARA CONTAGEM
Quando um ábaco está zerado, todas as miçangas ficam grudadas juntas. Quando há uma distância entre esse grupo de não movidos com outra miçanga, essa miçanga é considerada como movida. Você precisa ser minucioso, se tudo estiver com valores iguais diferentes de zero, desconfie. Se todas as linhas foram zero, também desconfie. Para ser contada, as miçangas precisam ter uma distância consideravel, não pode ser so um tiquinho. Além disso, eu posso ter mais de uma miçanga movida em uma coluna de um ábaco assim: 

###EXEMPLO
......  . ... --> 4 miçangas foram movidas
..........    --> 0 miçangas foram movidas
    ..........--> 10 miçangas movidas (vejo isso pois quando estavam zeradas, estavam juntas no lado oposto)
Uma miçanga ou mais miçangas podem ser consideradas como MOVIDAS quando estão deslocadas , distantes das demais miçangas na esquerda.

### FUNÇÃO
Sua função é contar a quantidade de miçangas movidas por um ser humano em cada linha e retornar os valores de forma estruturada (CSV). Contendo as seguintes colunas.
Coluna 1 - Tipo da concena (TOTAL|PARCIAL)
Coluna 3 - Categoria (representada ao meio do abaco)
Coluna 4 - Quantidade de miçangas MOVIDAS

IMPORTANTE
mande somente as informações pedidas (formato csv), para que eu possa passar isso para um arquivo. NAO PRECISA JUSTIFICAR SUA RESPOSTA

"""
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(keep_alive())
    yield

app = FastAPI(
    title="API de Análise de Ábaco com IA (Gemini)",
    description="Envia uma imagem de ábaco e recebe uma contagem estruturada em CSV e Excel usando IA.",
    version="1.1.0",
    lifespan=lifespan
)

app.include_router(health_router)

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head><title>API Ábaco - Gemini</title></head>
        <body>
            <h1>API de Análise de Ábaco</h1>
            <p>Use o endpoint <code>/analisar/</code> para enviar imagens</p>
            <p>Documentação: <a href="/docs">/docs</a></p>
        </body>
    </html>
    """

def analisar_imagem_pil(imagem: PIL.Image.Image):
    """Executa a análise da imagem com o prompt fixo"""
    try:
        response = model.generate_content([PROMPT_FIXO, imagem])
        return response.text
    except Exception as e:
        return f"Erro: {str(e)}"

@app.post("/analisar/")
async def analisar_imagem(file: UploadFile):
    """
    Envie uma imagem (.jpg ou .png). O sistema gera o CSV e também o Excel com os resultados.
    """
    excel_path = None  # Inicializa a variável
    try:
        conteudo = await file.read()
        imagem = PIL.Image.open(io.BytesIO(conteudo))

        resultado = analisar_imagem_pil(imagem)

        # === Converte texto CSV da IA para DataFrame ===
        try:
            df = pd.read_csv(io.StringIO(resultado))
        except Exception:
            # tenta com separador ponto e vírgula
            try:
                df = pd.read_csv(io.StringIO(resultado), sep=";")
            except Exception:
                # Se ainda falhar, cria um DataFrame com o erro
                df = pd.DataFrame({"Erro": [f"Não foi possível processar o resultado: {resultado}"]})

        # === Salva como Excel temporário ===
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            excel_path = tmp.name
            df.to_excel(excel_path, index=False, engine='openpyxl')

        # === Retorna JSON com link e preview ===
        return JSONResponse({
            "arquivo": file.filename,
            "resultado_csv": resultado,
            "excel_download": f"/download_excel/?path={excel_path}",
            "mensagem": "Análise concluída com sucesso! Clique no link para baixar o Excel."
        })

    except Exception as e:
        # Limpa o arquivo temporário em caso de erro
        if excel_path and os.path.exists(excel_path):
            os.unlink(excel_path)
        return JSONResponse(
            status_code=500,
            content={"erro": str(e)}
        )

@app.get("/download_excel/")
async def download_excel(path: str):
    """Permite baixar o Excel gerado"""
    try:
        if not os.path.exists(path):
            return JSONResponse(
                status_code=404,
                content={"erro": "Arquivo não encontrado"}
            )
        
        return FileResponse(
            path, 
            filename="resultado_abaco.xlsx", 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"erro": f"Erro ao baixar arquivo: {str(e)}"}
        )

# Limpeza de arquivos temporários (opcional)
@app.on_event("shutdown")
async def shutdown_event():
    """Limpa arquivos temporários ao desligar o servidor"""
    import glob
    temp_files = glob.glob("/tmp/*.xlsx")
    for file in temp_files:
        try:
            os.unlink(file)
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)