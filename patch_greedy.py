import re

with open('voice_app/api.py', 'r', encoding='utf-8') as f:
    code = f.read()

# We need to replace the section from "        # Greedy: sắp xếp tất cả" down to "            spk_identified[spk] = (name, score, email, user_info)"

pattern = re.compile(
    r'(        # Greedy: sắp xếp tất cả.*?spk_identified\[spk\] = \(name, score, email, user_info\))',
    re.DOTALL
)

replacement = """        is_single_chunk = not any(spk.startswith("c") and "_" in spk for spk in spk_embeddings)
        spk_identified = {}

        if is_single_chunk:
            for spk in spk_embeddings:
                if spk_ranked.get(spk):
                    best_name, best_score, email, user_info = spk_ranked[spk][0]
                    spk_identified[spk] = (best_name, best_score, email, user_info)
        else:
            # Greedy: sắp xếp tất cả (spk, name, score) theo score giảm dần
            all_candidates = []
            for spk, ranked in spk_ranked.items():
                for name, score, email, user_info in ranked:
                    all_candidates.append((score, spk, name, email, user_info))
            all_candidates.sort(key=lambda x: x[0], reverse=True)
    
            claimed_names_by_chunk = {}   # chunk_prefix -> {name: spk}
            claimed_spks  = set()  # spk đã được gán tên
    
            for score, spk, name, email, user_info in all_candidates:
                if spk in claimed_spks:
                    continue  # speaker này đã có tên rồi
                
                chunk_prefix = "all"
                if spk.startswith("c") and "_" in spk:
                    prefix = spk.split("_")[0]
                    if prefix[1:].isdigit():
                        chunk_prefix = prefix
    
                if chunk_prefix not in claimed_names_by_chunk:
                    claimed_names_by_chunk[chunk_prefix] = {}
    
                if name in claimed_names_by_chunk[chunk_prefix]:
                    print(f"[Speaker] Greedy: {spk}({score:.3f}) muốn '{name}' nhưng đã bị {claimed_names_by_chunk[chunk_prefix][name]} trong cùng chunk {chunk_prefix} claim → thử tiếp")
                    continue  # tên này đã bị người khác lấy trong cùng chunk, thử candidate tiếp theo
                    
                claimed_names_by_chunk[chunk_prefix][name] = spk
                claimed_spks.add(spk)
                spk_identified[spk] = (name, score, email, user_info)"""

if pattern.search(code):
    code = pattern.sub(replacement, code, count=1)
    with open('voice_app/api.py', 'w', encoding='utf-8') as f:
        f.write(code)
    print("Patched greedy successfully using regex")
else:
    print("Regex Target not found")
