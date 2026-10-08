"""Our own model as the proposer: a fine-tuned 7-8B prover served with vLLM (or Transformers).

The model is trained (kalima/train/) to map prompt -> JSON divisions, the same format as every
other proposer. Sampling several completions gives several divisions to try."""
from kalima.proposers.base import Proposer, prompt, parse


class HFModel(Proposer):
    def __init__(self, path, n=4, temperature=0.8, max_tokens=1024, backend="vllm"):
        self.path, self.n, self.temperature, self.max_tokens, self.backend = path, n, temperature, max_tokens, backend
        self.name = f"hf:{path}"
        if backend == "vllm":
            from vllm import LLM, SamplingParams
            self.llm = LLM(model=path, dtype="bfloat16")
            self.params = SamplingParams(n=n, temperature=temperature, max_tokens=max_tokens)
        else:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch
            self.tok = AutoTokenizer.from_pretrained(path)
            self.model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.bfloat16, device_map="auto")

    def propose(self, preamble, lemmas, goal, failed):
        p = prompt(preamble, lemmas, goal, failed)
        if self.backend == "vllm":
            texts = [o.text for o in self.llm.generate([p], self.params)[0].outputs]
        else:
            ids = self.tok(p, return_tensors="pt").to(self.model.device)
            outs = self.model.generate(**ids, do_sample=True, temperature=self.temperature, num_return_sequences=self.n,
                                       max_new_tokens=self.max_tokens)
            texts = [self.tok.decode(o[ids["input_ids"].shape[1]:], skip_special_tokens=True) for o in outs]
        divisions = [d for t in texts for d in parse(t)]
        return divisions, "\n---\n".join(texts)
