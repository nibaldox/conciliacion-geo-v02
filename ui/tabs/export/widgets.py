"""Streamlit widgets for the export tab."""
from contextlib import contextmanager
from typing import Any, Optional

import streamlit as st


def section_header(title: str, description: Optional[str] = None) -> None:
    st.subheader(title)
    if description:
        st.write(description)


def generate_button(label: str) -> bool:
    return st.button(label, type="primary")


def download_button(
    label: str,
    data: bytes,
    file_name: str,
    mime: str,
    type: Optional[str] = None,
) -> None:
    kwargs = {"label": label, "data": data, "file_name": file_name, "mime": mime}
    if type:
        kwargs["type"] = type
    st.download_button(**kwargs)


def success(message: str) -> None:
    st.success(message)


def warning(message: str) -> None:
    st.warning(message)


def progress_bar(value: float) -> Any:
    return st.progress(value)


@contextmanager
def spinner(message: str):
    with st.spinner(message):
        yield
