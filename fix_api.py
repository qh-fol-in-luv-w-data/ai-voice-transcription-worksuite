import re
with open('voice_app/api.py', 'r', encoding='utf-8') as f:
    text = f.read()

pattern = r'            merged_segments = \[\]\n            segments\.sort\(key=lambda x: x\["start"\]\).*?# Cleanup temp wav'
replacement = """            merged_segments = []
            segments.sort(key=lambda x: x["start"])

            for seg in segments:
                txt = " ".join(seg["text"].split())
                if not txt or not is_meaningful(txt):
                    continue
                spk_label = " ".join(speaker_cache.get(seg["speaker_id"], seg["speaker_id"]).split())
                emb = seg.get("embedding")

                if (merged_segments
                        and merged_segments[-1][2] == spk_label
                        and seg["start"] - merged_segments[-1][1] <= 1.5):
                    # Gộp vào segment trước, giữ embedding
                    prev_s, prev_e, prev_spk, prev_txt = merged_segments[-1][:4]
                    prev_emb = merged_segments[-1][4] if len(merged_segments[-1]) > 4 else emb
                    merged_segments[-1] = (prev_s, seg["end"], prev_spk, prev_txt + " " + txt, prev_emb)
                else:
                    merged_segments.append((seg["start"], seg["end"], spk_label, txt, emb))

            # Format results
            results = merged_segments[:]
            final_output_text = ""
            last_spk = None

            for s, e, spk_label, txt, *rest in results:
                if spk_label != last_spk:
                    final_output_text += f"\\n**{spk_label}** [{s:.1f}s]\\n{txt}"
                else:
                    final_output_text += f" {txt}"
                last_spk = spk_label

            # Cleanup temp wav"""

new_text = re.sub(pattern, replacement, text, flags=re.DOTALL)

with open('voice_app/api.py', 'w', encoding='utf-8') as f:
    f.write(new_text)

print('Fixed!')
