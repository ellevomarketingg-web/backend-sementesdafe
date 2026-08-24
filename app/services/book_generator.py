import os
from typing import Dict, Any, Optional, Tuple, List
import pymupdf as fitz
from app.core.config import settings
from app.core.logging import logger

PLACEHOLDER = "{nome}"


def _cor_rgb_para_fitz(cor_int: int) -> Tuple[float, float, float]:
    """Converte valor inteiro RGB retornado pelo PyMuPDF para tupla (r, g, b) no intervalo [0.0, 1.0]."""
    r = ((cor_int >> 16) & 255) / 255
    g = ((cor_int >> 8) & 255) / 255
    b = (cor_int & 255) / 255
    return (r, g, b)


def _fonte_compativel(nome_fonte_original: Optional[str]) -> str:
    """Mapeia o nome da fonte original para uma fonte padrão compatível no PyMuPDF."""
    nome = (nome_fonte_original or "").lower()
    negrito = "bold" in nome
    italico = "italic" in nome or "oblique" in nome

    if "times" in nome or "serif" in nome:
        base = "Times"
    elif "courier" in nome or "mono" in nome:
        base = "Courier"
    else:
        base = "Helvetica"

    if negrito and italico:
        return f"{base}-BoldOblique" if base != "Times" else "Times-BoldItalic"
    if negrito:
        return f"{base}-Bold"
    if italico:
        return f"{base}-Oblique" if base != "Times" else "Times-Italic"
    return base if base != "Times" else "Times-Roman"


def _extrair_fonte_embutida(doc: fitz.Document, pagina: fitz.Page, nome_fonte_pdf: str, cache: dict) -> Tuple[Optional[str], Optional[bytes]]:
    """Extrai os bytes da fonte embutida diretamente do PDF para preservar o design original."""
    if nome_fonte_pdf in cache:
        return cache[nome_fonte_pdf]

    resultado = (None, None)

    for info_fonte in pagina.get_fonts(full=True):
        xref = info_fonte[0]
        ext = info_fonte[1]
        basefont = info_fonte[3]

        if ext in ("n/a", "", None):
            continue

        if basefont == nome_fonte_pdf or nome_fonte_pdf in basefont or basefont in nome_fonte_pdf:
            try:
                extraido = doc.extract_font(xref)
                buffer = (
                    extraido[-1]
                    if isinstance(extraido, (tuple, list))
                    else extraido.get("content")
                )

                if buffer:
                    resultado = (f"F{xref}", buffer)
                    break
            except Exception:
                continue

    cache[nome_fonte_pdf] = resultado
    return resultado


def _ocorrencias_por_caractere(pagina: fitz.Page, placeholder: str = PLACEHOLDER) -> List[Dict[str, Any]]:
    """
    Localiza os caracteres do placeholder de forma estrita utilizando o 'rawdict',
    com margem de isolamento vertical (12%) para não tocar nem nas linhas vizinhas,
    nem nos caracteres adjacentes da mesma linha.
    """
    ocorrencias = []
    dados = pagina.get_text("rawdict")
    ph = placeholder.lower()
    ph_len = len(placeholder)

    for bloco in dados.get("blocks", []):
        for linha in bloco.get("lines", []):
            chars_da_linha = []

            for span in linha.get("spans", []):
                for c in span.get("chars", []):
                    chars_da_linha.append({
                        "c": c["c"],
                        "bbox": c["bbox"],
                        "font": span["font"],
                        "size": span["size"],
                        "color": span["color"],
                        "origin": c.get("origin", (c["bbox"][0], c["bbox"][3])),
                    })

            texto_linha = "".join(c["c"] for c in chars_da_linha).lower()
            start = 0

            while True:
                idx = texto_linha.find(ph, start)
                if idx == -1:
                    break

                grupo = chars_da_linha[idx: idx + ph_len]

                if grupo:
                    x0 = min(c["bbox"][0] for c in grupo)
                    y0 = min(c["bbox"][1] for c in grupo)
                    x1 = max(c["bbox"][2] for c in grupo)
                    y1 = max(c["bbox"][3] for c in grupo)

                    ref = grupo[0]
                    tamanho_fonte = ref["size"]

                    # Margem de segurança vertical (12%) para não encostar na linha inferior/superior
                    pad_y = tamanho_fonte * 0.12
                    y0_seguro = y0 + pad_y
                    y1_seguro = y1 - pad_y

                    # Ponto exato da linha de base (baseline)
                    baseline_y = ref["origin"][1] if "origin" in ref else y1

                    ocorrencias.append({
                        "rect_redact": fitz.Rect(x0, y0_seguro, x1, y1_seguro),
                        "orig_x0": x0,
                        "orig_x1": x1,
                        "orig_width": x1 - x0,
                        "baseline_y": baseline_y,
                        "fonte": ref["font"],
                        "tamanho": tamanho_fonte,
                        "cor": _cor_rgb_para_fitz(ref["color"]),
                    })

                start = idx + ph_len

    return ocorrencias


class BookGenerator:
    """
    Motor oficial de geração e validação de livros personalizados 'Deus Conhece o Seu Nome'.
    Implementa a lógica da v4 do notebook como fonte da verdade, com redaction transparente,
    isolamento de caracteres e preservação de design.
    """

    @classmethod
    def get_template_path(cls, gender_or_variant: Optional[str] = None) -> str:
        """
        Retorna o caminho do template PDF adequado (menino ou menina).
        """
        variant = (gender_or_variant or "").strip().lower()
        if variant in ("menina", "girl", "f", "feminino", "garota"):
            if os.path.exists(settings.BOOK_TEMPLATE_MENINA):
                return settings.BOOK_TEMPLATE_MENINA
        
        # Padrão: Menino
        if os.path.exists(settings.BOOK_TEMPLATE_MENINO):
            return settings.BOOK_TEMPLATE_MENINO
            
        # Fallback se apenas o de menina existir
        if os.path.exists(settings.BOOK_TEMPLATE_MENINA):
            return settings.BOOK_TEMPLATE_MENINA

        # Fallback genérico se arquivo estiver em outro diretório
        return settings.BOOK_TEMPLATE_MENINO

    @classmethod
    def validate_pdf_file(cls, file_path: str) -> bool:
        """Validação básica de integridade do arquivo gerado."""
        if not os.path.exists(file_path):
            return False
        if os.path.getsize(file_path) == 0:
            return False
        try:
            with open(file_path, "rb") as f:
                header = f.read(5)
                return header.startswith(b"%PDF-")
        except Exception as e:
            logger.error(f"Erro ao validar cabeçalho PDF {file_path}: {e}")
            return False

    @classmethod
    def validar_integridade(
        cls,
        caminho_template: str,
        caminho_saida: str,
        nome_crianca: str,
        placeholder: str = PLACEHOLDER,
        tolerancia_palavras: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Compara a contagem de palavras página a página entre template e saída.
        Garante que nenhum texto ao redor do placeholder foi apagado indevidamente.
        """
        if not os.path.exists(caminho_template) or not os.path.exists(caminho_saida):
            return []

        doc_t = fitz.open(caminho_template)
        doc_s = fitz.open(caminho_saida)
        suspeitas = []

        palavras_nome = max(1, len(nome_crianca.split()))

        for i in range(min(len(doc_t), len(doc_s))):
            texto_t = doc_t[i].get_text()
            texto_s = doc_s[i].get_text()

            n_placeholders = texto_t.lower().count(placeholder.lower())
            palavras_t = len(texto_t.split())
            palavras_s = len(texto_s.split())

            esperado = palavras_t - n_placeholders + (n_placeholders * palavras_nome)
            diferenca = abs(palavras_s - esperado)

            if diferenca > tolerancia_palavras:
                suspeitas.append({
                    "pagina": i + 1,
                    "placeholders_no_template": n_placeholders,
                    "palavras_esperadas": esperado,
                    "palavras_encontradas": palavras_s,
                    "diferenca": diferenca,
                })

        doc_t.close()
        doc_s.close()
        return suspeitas

    @classmethod
    def generate_book_pdf(
        cls,
        output_path: str,
        child_name: str,
        buyer_name: str = "",
        gender_or_variant: Optional[str] = None,
        custom_template_path: Optional[str] = None,
        custom_font_path: Optional[str] = None,
        tolerancia_largura: float = 1.3,
    ) -> bool:
        """
        Gera o livro personalizado 'Deus Conhece o Seu Nome' em PDF.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        display_child = child_name.strip() if child_name.strip() else "Querida Criança"
        template_path = custom_template_path or cls.get_template_path(gender_or_variant)
        font_path = custom_font_path or (settings.BOOK_DEFAULT_FONT if os.path.exists(settings.BOOK_DEFAULT_FONT) else None)

        if not os.path.exists(template_path):
            logger.warning(f"Template '{template_path}' não encontrado no disco. Criando fallback para ambiente de teste.")
            return cls._generate_fallback_pdf(output_path, display_child, buyer_name)

        try:
            doc = fitz.open(template_path)
            total_substituicoes = 0
            paginas_sem_match = []
            cache_fontes = {}

            for pagina in doc:
                ocorrencias = _ocorrencias_por_caractere(pagina, PLACEHOLDER)

                if not ocorrencias:
                    paginas_sem_match.append(pagina.number + 1)
                    continue

                preparo = []

                for oc in ocorrencias:
                    # Aplica redaction transparente delimitada apenas aos caracteres
                    pagina.add_redact_annot(oc["rect_redact"], fill=None)
                    preparo.append(oc)

                # Remove apenas os caracteres de texto demarcados sem tocar em imagens/vetores
                pagina.apply_redactions(images=0, graphics=0, text=0)

                for item in preparo:
                    tamanho = item["tamanho"]
                    fontname_custom = None
                    fontfile_custom = None
                    fontbuffer_custom = None

                    if font_path and os.path.exists(font_path):
                        fontname_custom = "FonteCustomizada"
                        fontfile_custom = font_path
                    else:
                        nome_interno, buffer = _extrair_fonte_embutida(
                            doc, pagina, item["fonte"], cache_fontes
                        )
                        if buffer:
                            fontname_custom = nome_interno
                            fontbuffer_custom = buffer

                    def medir(texto: str, tam: float) -> float:
                        if fontbuffer_custom:
                            return fitz.Font(fontbuffer=fontbuffer_custom).text_length(texto, fontsize=tam)
                        if fontfile_custom:
                            return fitz.Font(fontfile=fontfile_custom).text_length(texto, fontsize=tam)
                        return fitz.get_text_length(
                            texto,
                            fontname=_fonte_compativel(item["fonte"]),
                            fontsize=tam,
                        )

                    tamanho_final = tamanho
                    largura_nome = medir(display_child, tamanho_final)
                    largura_maxima = item["orig_width"] * tolerancia_largura

                    # Auto-encolhe suavemente se o nome for maior que a área original
                    while largura_nome > largura_maxima and tamanho_final > tamanho * 0.4:
                        tamanho_final -= 0.5
                        largura_nome = medir(display_child, tamanho_final)

                    pos_x = item["orig_x0"]
                    pos_y = item["baseline_y"]

                    if fontbuffer_custom:
                        pagina.insert_font(
                            fontname=fontname_custom,
                            fontbuffer=fontbuffer_custom,
                        )
                        pagina.insert_text(
                            fitz.Point(pos_x, pos_y),
                            display_child,
                            fontname=fontname_custom,
                            fontsize=tamanho_final,
                            color=item["cor"],
                        )
                    elif fontfile_custom:
                        pagina.insert_text(
                            fitz.Point(pos_x, pos_y),
                            display_child,
                            fontname=fontname_custom,
                            fontfile=fontfile_custom,
                            fontsize=tamanho_final,
                            color=item["cor"],
                        )
                    else:
                        pagina.insert_text(
                            fitz.Point(pos_x, pos_y),
                            display_child,
                            fontname=_fonte_compativel(item["fonte"]),
                            fontsize=tamanho_final,
                            color=item["cor"],
                        )

                    total_substituicoes += 1

            doc.save(output_path, garbage=4, deflate=True)
            doc.close()

            logger.info(f"Livro personalizado gerado: {output_path} ({total_substituicoes} substituições)")
            return True

        except Exception as e:
            logger.error(f"Erro ao processar template PDF com PyMuPDF: {e}", exc_info=True)
            return False

    @classmethod
    def _generate_fallback_pdf(cls, output_path: str, child_name: str, buyer_name: str) -> bool:
        """Gera um PDF estruturado simples caso o arquivo de template binário não esteja presente."""
        try:
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text(
                fitz.Point(50, 100),
                f"Deus Conhece o Seu Nome - {child_name}",
                fontsize=24,
                color=(0.1, 0.2, 0.6),
            )
            page.insert_text(
                fitz.Point(50, 150),
                f"Livro personalizado com amor por {buyer_name}",
                fontsize=14,
                color=(0.2, 0.2, 0.2),
            )
            doc.save(output_path)
            doc.close()
            return True
        except Exception as e:
            logger.error(f"Erro ao criar fallback PDF: {e}")
            return False
