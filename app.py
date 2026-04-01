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
# CONVERTIR NUMÉRICOS
# =========================
def convertir_numerico(serie):
    s = serie.astype(str).str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


# =========================
# NORMALIZAR NUMÉRICOS
# =========================
def normalizar_numericos(df):
    keywords = ["importe", "neto", "iva", "total", "tipo de cambio"]

    for col in df.columns:
        nombre = str(col).lower()

        if any(x in nombre for x in keywords):
            if df[col].dtype == object:
                df[col] = convertir_numerico(df[col])

    return df


# =========================
# DETECTAR COLUMNAS (MEJORADO)
# =========================
def detectar_columna(df, posibles):
    for col in df.columns:
        nombre = str(col).lower()
        for p in posibles:
            if p in nombre:
                return col
    return None


# =========================
# PROCESO
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
                    else:
                        st.warning(f"No se encontró archivo de compras en {uploaded_file.name}")

        if not dataframes:
            st.error("No se encontraron datos")
            st.stop()

        df_final = pd.concat(dataframes, ignore_index=True)

        # =========================
        # NORMALIZACIÓN
        # =========================
        df_final = normalizar_numericos(df_final)

        # =========================
        # DETECCIÓN CORRECTA
        # =========================
        col_fecha = detectar_columna(df_final, ["fecha de emisión", "fecha"])
        
        col_cuit = detectar_columna(df_final, [
            "nro. doc. vendedor",
            "nro doc vendedor",
            "numero doc vendedor",
            "cuit"
        ])

        col_nombre = detectar_columna(df_final, [
            "denominación vendedor",
            "denominacion vendedor",
            "razón social",
            "razon social",
            "proveedor"
        ])

        col_importe = detectar_columna(df_final, [
            "importe total",
            "importe"
        ])

        # DEBUG CLAVE
        st.write("Columnas detectadas:")
        st.write({
            "fecha": col_fecha,
            "cuit": col_cuit,
            "nombre": col_nombre,
            "importe": col_importe
        })

        # =========================
        # LIMPIEZAS
        # =========================
        if col_fecha:
            df_final[col_fecha] = pd.to_datetime(df_final[col_fecha], errors="coerce")

        if col_cuit:
            df_final[col_cuit] = df_final[col_cuit].apply(limpiar_cuit)

        # =========================
        # VALIDACIÓN FUERTE
        # =========================
        if col_cuit is None:
            st.error("❌ No se detectó columna de CUIT")
            st.write(df_final.columns.tolist())
            st.stop()

        if col_importe is None:
            st.error("❌ No se detectó columna de importe")
            st.write(df_final.columns.tolist())
            st.stop()

        if col_nombre is None:
            st.warning("⚠️ No se detectó nombre → se usará CUIT")
            df_final["Proveedor_TMP"] = df_final[col_cuit]
            col_nombre = "Proveedor_TMP"

        # =========================
        # PADRÓN
        # =========================
        base = df_final[[col_cuit, col_nombre, col_importe]].copy()

        base["CUIT"] = base[col_cuit].astype(str)
        base["Proveedor"] = base[col_nombre].astype(str)
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
            padron.to_excel(writer, sheet_name="Padron_Proveedores", index=False)

        with open(output, "rb") as f:
            st.download_button(
                "📥 Descargar Excel",
                f,
                file_name="compras_unificadas.xlsx"
            )

        st.success(f"✅ OK → {len(df_final)} registros | {len(padron)} proveedores")
