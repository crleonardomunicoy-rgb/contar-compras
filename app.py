import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile

st.title("📊 Contar - Unificación de Compras")

uploaded_files = st.file_uploader(
    "Subí los archivos ZIP de ARCA",
    type="zip",
    accept_multiple_files=True
)

# 🔧 Función para leer CSV con distintos encodings
def leer_csv_seguro(file):
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            file.seek(0)
            return pd.read_csv(file, sep=";", encoding=encoding)
        except:
            continue
    raise Exception("No se pudo leer el archivo con ningún encoding")

# 🔧 Función para normalizar números (AFIP → Excel correcto)
def normalizar_numeros(df):
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace('.', '', regex=False)   # miles
                    .str.replace(',', '.', regex=False)  # decimal
                )
                df[col] = pd.to_numeric(df[col], errors='ignore')
            except:
                pass
    return df

if uploaded_files:
    if st.button("Unificar archivos"):

        dataframes = []

        with tempfile.TemporaryDirectory() as temp_dir:

            for uploaded_file in uploaded_files:
                zip_path = os.path.join(temp_dir, uploaded_file.name)

                # Guardar ZIP temporalmente
                with open(zip_path, "wb") as f:
                    f.write(uploaded_file.read())

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:

                    archivos = zip_ref.namelist()
                    archivo_compras = None

                    # 🔎 Buscar CSV de compras (aunque esté en subcarpetas)
                    for file in archivos:
                        nombre = file.lower()
                        if "comprobantes_compras" in nombre and file.endswith(".csv"):
                            archivo_compras = file
                            break

                    if archivo_compras:
                        try:
                            with zip_ref.open(archivo_compras) as f:

                                df = leer_csv_seguro(f)

                                # 📅 Extraer período del nombre del ZIP
                                nombre_zip = uploaded_file.name.lower()
                                periodo = nombre_zip.replace("libro_iva_periodo_", "")
                                periodo = periodo.replace("_original.zip", "")

                                df["Periodo"] = periodo
                                df["Archivo_Origen"] = uploaded_file.name
                                df["Archivo_CSV"] = archivo_compras

                                dataframes.append(df)

                        except Exception as e:
                            st.error(f"❌ Error leyendo {archivo_compras}: {e}")

                    else:
                        st.warning(f"⚠️ No se encontró comprobantes_compras.csv en {uploaded_file.name}")

        if dataframes:

            df_final = pd.concat(dataframes, ignore_index=True)

            # 🔢 NORMALIZAR NÚMEROS (CLAVE)
            df_final = normalizar_numeros(df_final)

            # 📅 Ordenar por fecha si existe
            posibles_fechas = [
                "Fecha de Emisión",
                "fecha",
                "Fecha"
            ]

            for col in posibles_fechas:
                if col in df_final.columns:
                    try:
                        df_final[col] = pd.to_datetime(df_final[col], errors="coerce")
                        df_final = df_final.sort_values(by=col)
                        break
                    except:
                        pass

            # 📁 Exportar Excel
            output_path = os.path.join(tempfile.gettempdir(), "compras_unificadas.xlsx")

            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, sheet_name="Compras_Unificadas", index=False)

            # 📥 Descargar
            with open(output_path, "rb") as f:
                st.download_button(
                    "📥 Descargar Excel",
                    f,
                    file_name="compras_unificadas.xlsx"
                )

            st.success(f"✅ {len(df_final)} registros procesados correctamente")

        else:
            st.warning("⚠️ No se encontraron datos de compras en los archivos cargados")
