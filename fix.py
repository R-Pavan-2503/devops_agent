with open("d:\\projects\\ai_agents\\try_1\\10-agent-devops\\agents\\nodes.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if line.strip() == "else:" and "except Exception:" in lines[i-2]:
        new_lines.append('            print("   [Knowledge Map] Missing map. Triggering Wiki Builder bootstrap...")\n')
        new_lines.append('            generated = generate_knowledge_map(\n')
        new_lines.append('                repo_name=repo_name,\n')
        new_lines.append('                workspace_path=workspace_path,\n')
        new_lines.append('                repo_map_str=repo_map_str,\n')
        new_lines.append('                commit_sha=commit_sha,\n')
        new_lines.append('                wiki_builder_llm=wiki_builder_llm,\n')
        new_lines.append('            )\n')
        new_lines.append('            knowledge_context_str = generated["knowledge_context_str"]\n')
        new_lines.append('\n')
        new_lines.append('        context_gathered = (\n')
        new_lines.append('            f"[Layer 1 Repo Map]\\n{repo_map_str[:4000]}\\n\\n"\n')
        new_lines.append('            f"[Layer 2 Knowledge Map]\\n{knowledge_context_str[:2000]}"\n')
        new_lines.append('        )\n')
        new_lines.append('        context_to_save = context_gathered\n')
        new_lines.append('\n')
        new_lines.append('    final_messages = [\n')
        new_lines.append('        SystemMessage(content=ARCHITECT_AGENT_PROMPT),\n')
        new_lines.append('        HumanMessage(content=(\n')
        new_lines.append('            f"Repository: {repo_name}\\n\\n"\n')
        new_lines.append('            f"Review this pull request code:\\n\\n{code}\\n\\n"\n')
        new_lines.append('            f"Relevant codebase patterns for reference:\\n{context_gathered}"\n')
        new_lines.append('        ))\n')
        new_lines.append('    ]\n')

with open("d:\\projects\\ai_agents\\try_1\\10-agent-devops\\agents\\nodes.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
