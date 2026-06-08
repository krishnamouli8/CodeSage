import torch
from transformers import AutoTokenizer, AutoModel

class Embedder:
    def __init__(self, model_name: str = "microsoft/unixcoder-base"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()

    def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Returns a list of 768-dim float32 embeddings."""
        embeddings = []
        
        if not texts:
            return embeddings
            
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                
                inputs = self.tokenizer(
                    batch_texts,
                    max_length=512,
                    padding=True,
                    truncation=True,
                    return_tensors="pt"
                ).to(self.device)
                
                outputs = self.model(**inputs)
                
                # Mean-pooling over the last hidden state
                # outputs.last_hidden_state shape: (batch_size, sequence_length, hidden_size)
                # We use attention_mask to ignore padding tokens
                attention_mask = inputs["attention_mask"].unsqueeze(-1).expand(outputs.last_hidden_state.size()).float()
                sum_embeddings = torch.sum(outputs.last_hidden_state * attention_mask, 1)
                sum_mask = torch.clamp(attention_mask.sum(1), min=1e-9)
                batch_embeddings = sum_embeddings / sum_mask
                
                embeddings.extend(batch_embeddings.cpu().numpy().tolist())
                
        return embeddings
