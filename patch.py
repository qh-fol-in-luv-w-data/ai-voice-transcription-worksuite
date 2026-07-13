import re

with open('voice_app/api.py', 'r', encoding='utf-8') as f:
    code = f.read()

# PATCH 1: Bypass greedy
target_greedy = """        # Greedy: sắp xếp tất cả (spk, name, score) theo score giảm dần
        all_candidates = []
        for spk, ranked in spk_ranked.items():
            for name, score, email, user_info in ranked:
                all_candidates.append((score, spk, name, email, user_info))
        all_candidates.sort(key=lambda x: x[0], reverse=True)

        claimed_names_by_chunk = {}   # chunk_prefix -> {name: spk}
        claimed_spks  = set()  # spk đã được gán tên
        spk_identified = {}

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

replacement_greedy = """        is_single_chunk = not any(spk.startswith("c") and "_" in spk for spk in spk_embeddings)
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

code = code.replace(target_greedy, replacement_greedy)

# PATCH 2: Bypass Merge threshold
target_merge = """        groups = []
        if strangers:
            valid_strangers = [spk for spk in strangers if spk in spk_embeddings]
            missing_strangers = [spk for spk in strangers if spk not in spk_embeddings]"""

replacement_merge = """        groups = []
        if strangers:
            if is_single_chunk:
                for spk in strangers:
                    groups.append([spk])
            else:
                valid_strangers = [spk for spk in strangers if spk in spk_embeddings]
                missing_strangers = [spk for spk in strangers if spk not in spk_embeddings]"""

code = code.replace(target_merge, replacement_merge)

# Cẩn thận thụt lề cho khối else của strangers
target_indent = """                import re
                import numpy as np
                def get_chunk_idx(s):
                    m = re.match(r'c(\d+)_', s)
                    return int(m.group(1)) if m else 0
                
                # Sắp xếp speaker theo chunk: ưu tiên xử lý c0 trước, rồi c1, c2...
                valid_strangers.sort(key=lambda x: (get_chunk_idx(x), x))
                
                # Thuật toán Gom Nhóm Ràng Buộc (Constrained Clustering):
                # 1. Không bao giờ gộp 2 speaker trong CÙNG 1 chunk.
                # 2. Người lạ ở chunk sau sẽ tìm group ở chunk trước có độ giống cao nhất.
                groups = []
                for spk in valid_strangers:
                    chunk_idx = get_chunk_idx(spk)
                    emb = spk_embeddings[spk]
                    
                    best_sim = -1
                    best_group_idx = -1
                    
                    for i, grp in enumerate(groups):
                        # RÀNG BUỘC CỐT LÕI: Group này đã có 1 người ở chunk hiện tại thì CẤM gộp thêm!
                        if any(get_chunk_idx(member) == chunk_idx for member in grp):
                            continue
                            
                        # Tính similarity với vector trung bình của group
                        grp_emb = np.mean([spk_embeddings[m] for m in grp], axis=0)
                        norm = np.linalg.norm(grp_emb)
                        if norm > 0: grp_emb /= norm
                        
                        sim = np.dot(emb, grp_emb)
                        if sim > best_sim:
                            best_sim = sim
                            best_group_idx = i
                            
                    if best_sim >= MERGE_THRESHOLD:
                        groups[best_group_idx].append(spk)
                    else:
                        groups.append([spk])
                    
                # Những người không có âm thanh (không có embedding) thì mỗi người tự thành 1 nhóm riêng
                for spk in missing_strangers:
                    groups.append([spk])"""

replacement_indent = """                import re
                import numpy as np
                def get_chunk_idx(s):
                    m = re.match(r'c(\d+)_', s)
                    return int(m.group(1)) if m else 0
                
                # Sắp xếp speaker theo chunk: ưu tiên xử lý c0 trước, rồi c1, c2...
                valid_strangers.sort(key=lambda x: (get_chunk_idx(x), x))
                
                # Thuật toán Gom Nhóm Ràng Buộc (Constrained Clustering):
                # 1. Không bao giờ gộp 2 speaker trong CÙNG 1 chunk.
                # 2. Người lạ ở chunk sau sẽ tìm group ở chunk trước có độ giống cao nhất.
                groups = []
                for spk in valid_strangers:
                    chunk_idx = get_chunk_idx(spk)
                    emb = spk_embeddings[spk]
                    
                    best_sim = -1
                    best_group_idx = -1
                    
                    for i, grp in enumerate(groups):
                        # RÀNG BUỘC CỐT LÕI: Group này đã có 1 người ở chunk hiện tại thì CẤM gộp thêm!
                        if any(get_chunk_idx(member) == chunk_idx for member in grp):
                            continue
                            
                        # Tính similarity với vector trung bình của group
                        grp_emb = np.mean([spk_embeddings[m] for m in grp], axis=0)
                        norm = np.linalg.norm(grp_emb)
                        if norm > 0: grp_emb /= norm
                        
                        sim = np.dot(emb, grp_emb)
                        if sim > best_sim:
                            best_sim = sim
                            best_group_idx = i
                            
                    if best_sim >= MERGE_THRESHOLD:
                        groups[best_group_idx].append(spk)
                    else:
                        groups.append([spk])
                    
                # Những người không có âm thanh (không có embedding) thì mỗi người tự thành 1 nhóm riêng
                for spk in missing_strangers:
                    groups.append([spk])"""

# indent the target_indent block by 4 spaces
indented = "\n".join("    " + line if line.strip() else line for line in target_indent.split("\n"))
code = code.replace(target_indent, indented)


with open('voice_app/api.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patched successfully")
