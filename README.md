# Validación de Reporte

## Requisitos para el entorno

- Python 3.8+
- Pandas, openpyxl

### Se puede ejecutar de dos formas:
### Opción 1: Desde GitHub Actions
1. Ve a [Actions - Validar Datos de Prueba](https://github.com/titortizc/falabella-datos/actions/workflows/validar.yml)
2. Click en **Run workflow** → **Run workflow**
3. Espera a que termine
4. Descarga el log `hallazgos-log` en Artifacts

### Opción 2: Local
1. Descargar el repositorio manual
(https://github.com/titortizc/falabella-datos)

O clonar
git clone https://github.com/titortizc/falabella-datos.git

2. En bash ejecutar para descargar librerias
pip install pandas openpyxl

3. Ejecución bash para generar la validación
python validacion_reportes.py

4. Ejecutado el bash del paso 3 se genera reportería hallazgos.log
