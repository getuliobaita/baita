"""Interface do fallback de OCR (quando o QR nao e legivel) + mock.

Regra fixa da spec: nunca creditar coins so com base em OCR sem confirmar a
chave de acesso extraida na SEFAZ -- este adapter so tenta *ler* a chave da
imagem; a validacao continua sempre passando pelo SefazAdapter depois.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional


class OcrAdapter(ABC):
    @abstractmethod
    def extrair_chave_acesso(self, imagem_base64: str) -> Optional[str]:
        """Retorna a chave de 44 digitos se conseguir ler, ou None."""
        ...


class MockOcrAdapter(OcrAdapter):
    """Sem servico de OCR real (nenhuma credencial/API fornecida). Por
    padrao 'nao consegue ler nada' -- forca o caminho de revisao_manual,
    que e o comportamento mais seguro na ausencia de OCR de verdade.
    Testes podem programar uma leitura especifica via `programar_leitura`."""

    def __init__(self) -> None:
        self._leituras: Dict[str, Optional[str]] = {}

    def programar_leitura(self, imagem_base64: str, chave_acesso: Optional[str]) -> None:
        self._leituras[imagem_base64] = chave_acesso

    def extrair_chave_acesso(self, imagem_base64: str) -> Optional[str]:
        return self._leituras.get(imagem_base64)

    def reset(self) -> None:
        self._leituras.clear()
