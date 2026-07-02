from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutreachDraftPrompt:
    system_prompt: str
    user_prompt: str


def build_outreach_draft_prompt(
    *,
    locale: str,
    company: str,
    contact_name: str,
    title: str,
    industry: str,
    website: str,
    source: str,
    notes: str = "",
) -> OutreachDraftPrompt:
    if locale == "en-US":
        system = (
            "You write concise B2B outreach email drafts. Return only a subject line "
            "and plain text body. Do not claim facts not provided. Do not send email."
        )
        user = (
            "Create an outreach draft for this lead.\n"
            f"Company: {_clean(company)}\n"
            f"Contact: {_clean(contact_name)}\n"
            f"Title: {_clean(title)}\n"
            f"Industry: {_clean(industry)}\n"
            f"Website: {_clean(website)}\n"
            f"Lead source: {_clean(source)}\n"
            f"Additional instruction: {_clean(notes)}\n"
            "Format:\nSubject: ...\n\nBody..."
        )
    else:
        system = (
            "你是一名克制、专业的 B2B 外联邮件草稿助手。只返回邮件主题和纯文本正文。"
            "不要编造未提供的事实。不要发送邮件。"
        )
        user = (
            "请为以下线索生成一封外联邮件草稿。\n"
            f"公司：{_clean(company)}\n"
            f"联系人：{_clean(contact_name)}\n"
            f"职位：{_clean(title)}\n"
            f"行业：{_clean(industry)}\n"
            f"网站：{_clean(website)}\n"
            f"线索来源：{_clean(source)}\n"
            f"补充要求：{_clean(notes)}\n"
            "格式：\n主题：...\n\n正文..."
        )
    return OutreachDraftPrompt(system_prompt=system, user_prompt=user)


def _clean(value: str) -> str:
    return (value or "").strip()[:500]
