def extract_features(feature_string):
    if feature_string and len(feature_string):
        assert feature_string.startswith("[") and feature_string.endswith("]")
        features = [f.strip() for f in feature_string[1:-1].split(",")]
    else:
        features = []

    selected_features = {}
    for f in features:
        if f.startswith("~"):
            selected_features[f[1:]] = False
        else:
            selected_features[f] = True
    return selected_features
