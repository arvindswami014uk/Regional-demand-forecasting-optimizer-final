# Dashboard Deployment Guide

## Streamlit Cloud deploy

1. Push the repository to GitHub with `streamlit_app.py`, `.streamlit/config.toml`, and `requirements_streamlit.txt` committed.
2. In Streamlit Cloud, create a new app and point it to this repository with `streamlit_app.py` as the entrypoint.
3. Confirm the app starts, then verify the filters and Plotly charts load from the processed CSV outputs.

## Hugging Face Spaces deploy

1. Create a new Space and choose the Streamlit SDK.
2. Connect or upload this repository content into the Space.
3. Keep `streamlit_app.py` at the project root so the default app entrypoint is obvious.
4. Add the dependencies from `requirements_streamlit.txt` to the Space environment.
5. Launch the Space and test the region, category, and week filters after the build finishes.

Expected Hugging Face Spaces URL format:

- `https://huggingface.co/spaces/arvindswami014uk/demand-forecasting-dashboard`

## Quick checks after deploy

- The app opens without missing-file errors.
- KPI values show 134, 11,461, \$14,831.57, and 33.37.
- The forecast, warehouse, ABC-XYZ, safety stock, and holding-cost charts render correctly.
- The methodology expander shows the source usage summary.

_Deployment guide updated: 2026-04-23T20:49:22.902592+00:00_