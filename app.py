import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile

st.title("📊 Contar - Unificación de Compras")

uploaded_files = st.file_uploader(
    "Subí los archivos ZIP",
    type="zip",
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Unificar archivos"):
        dataframes = []

        with tempfile.TemporaryDirectory() as temp_dir:

            for uploaded_file in uploaded_files:
                zip_path = os.path.join(temp_dir, uploaded_file.name)

                with open(zip_path, "wb") as f:
                    f.write(uploaded_file.read())

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)

                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file == "comprobantes_compras.csv":
                            ruta_csv = os.path.join(root, file)

                            try:
                                df = pd.read_csv(ruta_csv, sep=';', encoding='utf-8')

                                periodo = uploaded_file.name.replace("libro_iva_periodo_", "").replace("_original.zip", "")
                                df["Periodo"] = periodo
                                df["Archivo_Origen"] = uploaded_file.name

                                dataframes.append(df)

                            except Exception as e:
                                st.error(f"Error en {file}: {e}")

        if dataframes:
            df_final = pd.concat(dataframes, ignore_index=True)

            output_path = os.path.join(tempfile.gettempdir(), "compras_unificadas.xlsx")
            df_final.to_excel(output_path, index=False)

            with open(output_path, "rb") as f:
                st.download_button(
                    "📥 Descargar Excel",
                    f,
                    file_name="compras_unificadas.xlsx"
                )
        else:
            st.warning("No se encontraron archivos")
