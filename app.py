import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile

st.title("📊 Contar - Unificación de Compras + Padrón")

uploaded_files = st.file_uploader(
    "Subí los archivos ZIP de ARCA",
    type="zip",
    accept_multiple_files=True
)

# =========================
# LECTURA CSV SEGURA
# =========================
def leer_csv_seguro(file):
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            file.seek(0)
            df = pd.read_csv(
                file,
                sep=";",
                encoding=encoding,
                decimal=",",
                thousands="."
            )
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except:
            continue
    raise Exception("No se pudo leer el CSV")


# =========================
# LIMPIAR CUIT
# =========================
def limpiar_cuit(valor):
    if pd.isna(valor):
        return ""
    return "".join(ch for ch in str(valor) if ch.isdigit())


# =========================
# CONVERTIR A NUMÉRICO BIEN
# =========================
def convertir_numerico(serie):
    s = serie.astype(str).str.strip()

    s = s.replace({
        "": pd.NA,
        "nan": pd.NA,
        "None": pd.NA,
        "<NA>": pd.NA
    })

    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)

    return pd.to_numeric(s, errors="coerce")


# =========================
# NORMALIZAR COLUMNAS NUMÉRICAS
# =========================
def normalizar_numericos(df):
    keywords = [
        "importe", "neto", "iva", "total",
        "percepción", "retención", "tipo de cambio"
    ]

    excluir = [
        "denominación", "proveedor", "vendedor"
    ]

    for col in df.columns:
        nombre = str(col).lower()

        if any(x in nombre for x in excluir):
            continue

        if any(x in nombre for x in keywords):
            if df[col].dtype == object:
                convertido = convertir_numerico(df[col])
                if convertido.notna().sum() > 0:
                    df[col] = convertido

    return df


# =========================
# DETECTORES
# =========================
def detectar(df, palabras):
    for col in df.columns:
        nombre = str(col).lower()
        if any(p in nombre for p in palabras):
            return col
    return None


# =========================
# PROCESO PRINCIPAL
# =========================
if uploaded_files:
    if st.button("Procesar"):

        dataframes = []

        with tempfile.TemporaryDirectory() as temp_dir:
            for uploaded_file in uploaded_files:

                zip_path = os.path.join(temp_dir, uploaded_file.name)

                with open(zip_path, "wb") as f:
                    f.write(uploaded_file.read())

                with zipfile.ZipFile(zip_path, "r") as zip_ref:

                    archivo = None

                    for f in zip_ref.namelist():
                        if "comprobantes_compras" in f.lower():
                            archivo = f
                            break

                    if archivo:
                        with zip_ref.open(archivo) as f:
                            df = leer_csv_seguro(f)

                            periodo = uploaded_file.name.replace(
                                "libro_iva_periodo_", ""
                            ).replace("_original.zip", "")

                            df["Periodo"] = periodo
                            df["Archivo"] = uploaded_file.name

                            dataframes.append(df)

        df_final = pd.concat(dataframes, ignore_index=True)

        # =========================
        # NORMALIZACIÓN
        # =========================
        df_final = normalizar_numericos(df_final)

        col_fecha = detectar(df_final, ["fecha"])
        col_cuit = detectar(df_final, ["doc vendedor", "cuit"])
        col_nombre = detectar(df_final, ["denominación", "proveedor", "vendedor"])
        col_importe = detectar(df_final, ["importe total", "importe"])

        # Fecha
        if col_fecha:
            df_final[col_fecha] = pd.to_datetime(df_final[col_fecha], errors="coerce")

        # CUIT limpio
        if col_cuit:
            df_final[col_cuit] = df_final[col_cuit].apply(limpiar_cuit)

        # =========================
        # PADRÓN
        # =========================
        padron = pd.DataFrame()

        if col_cuit and col_nombre and col_importe:

            base = df_final[[col_cuit, col_nombre, col_importe]].copy()

            base["CUIT"] = base[col_cuit]
            base["Proveedor"] = base[col_nombre]
            base["Importe"] = pd.to_numeric(base[col_importe], errors="coerce").fillna(0)

            base = base[base["CUIT"] != ""]

            padron = base.groupby("CUIT").agg(
                Proveedor=("Proveedor", "last"),
                Cantidad_Comprobantes=("CUIT", "count"),
                Importe_Total=("Importe", "sum")
            ).reset_index()

            padron = padron.sort_values(by="Importe_Total", ascending=False)

        # =========================
        # EXPORTAR
        # =========================
        output = os.path.join(tempfile.gettempdir(), "compras_unificadas.xlsx")

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

            df_final.to_excel(writer, sheet_name="Compras_Unificadas", index=False)

            if not padron.empty:
                padron.to_excel(writer, sheet_name="Padron_Proveedores", index=False)

        with open(output, "rb") as f:
            st.download_button(
                "📥 Descargar Excel",
                f,
                file_name="compras_unificadas.xlsx"
            )

        st.success("✅ Archivo generado correctamente")
