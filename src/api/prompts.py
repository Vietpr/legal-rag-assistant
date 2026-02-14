SYSTEM_PROMPT = """Bạn là một trợ lý pháp lý AI chuyên về luật Việt Nam.

## NGUYÊN TẮC BẮT BUỘC:

1. **CHỈ trả lời dựa trên các Điều luật được cung cấp trong phần CONTEXT bên dưới.**
   - KHÔNG được tự suy luận hoặc thêm thông tin ngoài context.
   - Nếu context không đủ để trả lời, hãy nói rõ: "Tôi không tìm thấy thông tin đủ trong các điều luật được cung cấp."

2. **Trích dẫn rõ ràng** — Mỗi thông tin phải kèm:
   - Tên luật / Nghị định
   - Số Điều, Khoản, Điểm (nếu có)
   - Năm ban hành
   - Ví dụ: "Theo Điều 3, Khoản 1 Nghị định 74/2024/NĐ-CP, ..."

3. **Ưu tiên luật mới nhất** — Nếu có nhiều Điều liên quan, ưu tiên trích dẫn từ văn bản có năm ban hành gần nhất.

4. **Trả lời bằng tiếng Việt**, rõ ràng, dễ hiểu, có cấu trúc.

5. **Định dạng câu trả lời:**
   - Tóm tắt ngắn gọn ở đầu
   - Chi tiết với trích dẫn cụ thể
   - Nêu rõ nguồn (tên luật + năm) ở cuối
"""


def build_context(chunks: list[dict]) -> str:
    """Build context string from search results for the prompt."""
    context_parts = []

    for i, chunk in enumerate(chunks, 1):
        law_title = chunk.get("law_title", "N/A")
        law_type = chunk.get("law_type", "N/A")
        chapter = chunk.get("chapter", "")
        article = chunk.get("article", "N/A")
        year = chunk.get("issued_year", "N/A")
        version = chunk.get("version", "")
        text = chunk.get("text", "")

        # Keep Vietnamese labels here since they are part of the legal prompt content
        part = f"""--- Nguồn {i} ---
Luật: {law_title} ({law_type}, {year})
Chương: {chapter or 'N/A'}
Điều: {article}
Phiên bản: {version}

{text}
"""
        context_parts.append(part)

    return "\n".join(context_parts)


def build_prompt(question: str, chunks: list[dict]) -> str:
    """Build full prompt = context + question."""
    context = build_context(chunks)

    # Keep Vietnamese prompt text since it instructs the LLM to respond in Vietnamese
    return f"""## CONTEXT (Các Điều luật liên quan):

{context}

## CÂU HỎI:
{question}

## TRẢ LỜI:
Hãy trả lời câu hỏi trên dựa trên các Điều luật trong CONTEXT. Trích dẫn rõ Điều/Khoản/tên luật/năm.
"""
