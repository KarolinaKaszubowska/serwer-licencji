import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google import genai
from google.genai import types
from supabase import create_client, Client

app = FastAPI()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


class ZadanieAnalizy(BaseModel):
    licencja: str
    prompt: str


class ZadanieAnalizyRynku(BaseModel):
    licencja: str
    prompt: str
    system_instruction: str = "Jesteś analitykiem finansowym."


class ZadanieSprawdzenia(BaseModel):
    licencja: str


@app.get("/")
def health_check():
    return {"status": "Serwer licencyjny AnalizatorSF działa poprawnie."}


@app.post("/api/sprawdz-licencje")
def sprawdz_licencje(dane: ZadanieSprawdzenia):
    res = supabase.table("licencje").select("*").eq("klucz", dane.licencja.strip()).execute()
    if not res.data or not res.data[0].get("aktywna"):
        raise HTTPException(status_code=401, detail="Nieprawidłowy lub nieaktywny klucz licencyjny.")
    rekord = res.data[0]
    return {
        "aktywna": True,
        "limit_analiz": rekord["limit_analiz"],
        "uzyte_analizy": rekord["uzyte_analizy"],
        "pozostalo": max(0, rekord["limit_analiz"] - rekord["uzyte_analizy"]),
    }


@app.post("/api/analiza")
def wykonaj_analize(dane: ZadanieAnalizy):
    klucz = dane.licencja.strip()
    res = supabase.table("licencje").select("*").eq("klucz", klucz).execute()

    if not res.data or not res.data[0].get("aktywna"):
        raise HTTPException(status_code=401, detail="Nieprawidłowy lub nieaktywny klucz licencyjny.")

    rekord = res.data[0]
    limit_analiz = rekord["limit_analiz"]
    uzyte_analizy = rekord["uzyte_analizy"]

    if uzyte_analizy >= limit_analiz:
        raise HTTPException(
            status_code=403,
            detail="Limit analiz w pakiecie został wyczerpany. Dokup pakiet lub wpisz własny klucz API.",
        )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",  # lub "gemini-3.8-flash"
            contents=dane.prompt,
        )
        tekst_raportu = response.text
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Błąd komunikacji z Gemini API: {str(e)}")

    nowe_uzyte = uzyte_analizy + 1
    supabase.table("licencje").update({"uzyte_analizy": nowe_uzyte}).eq("klucz", klucz).execute()

    return {
        "tekst_raportu": tekst_raportu,
        "pozostalo_analiz": limit_analiz - nowe_uzyte,
    }

@app.post("/api/analiza-rynku")
def wykonaj_analize_rynku(dane: ZadanieAnalizyRynku):
    try:
        klucz = dane.licencja.strip()
        res = supabase.table("licencje").select("*").eq("klucz", klucz).execute()

        if not res.data or not res.data[0].get("aktywna"):
            raise HTTPException(status_code=401, detail="Nieprawidłowy lub nieaktywny klucz licencyjny.")

        rekord = res.data[0]
        limit_analiz = rekord["limit_analiz"]
        uzyte_analizy = rekord["uzyte_analizy"]

        if uzyte_analizy >= limit_analiz:
            raise HTTPException(
                status_code=403,
                detail="Limit analiz w pakiecie został wyczerpany. Dokup pakiet lub wpisz własny klucz API.",
            )

        # Używamy modelu gemini-3.1-pro-preview spójnego z resztą aplikacji
        response = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=dane.prompt,
            config=types.GenerateContentConfig(
                system_instruction=dane.system_instruction,
                temperature=0.0,
                tools=[{"google_search": {}}],
            ),
        )
        tekst_raportu = response.text

        nowe_uzyte = uzyte_analizy + 1
        supabase.table("licencje").update({"uzyte_analizy": nowe_uzyte}).eq("klucz", klucz).execute()

        return {
            "tekst_raportu": tekst_raportu,
            "pozostalo_analiz": limit_analiz - nowe_uzyte,
        }
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print("--- SZCZEGÓŁY BŁĘDU PYTHON ---")
        print(error_details)
        print("------------------------------")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")
