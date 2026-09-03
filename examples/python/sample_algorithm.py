class SampleQuotientFamilial:
    def run(self, data):
        agent = data.get("agent_revenu", 0) or 0
        conj = data.get("conjoint_revenu") or 0
        children = data.get("agent_enfants", 0) or 0
        denom = max(1, children + 1)
        value = (agent + conj) / denom
        explanation = f"Computed ({agent}+{conj})/{denom}"
        return {"value": f"{value:.2f}€", "explanation": explanation}
