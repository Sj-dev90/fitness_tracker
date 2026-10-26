import math
import random
from datetime import datetime

def calculate_1rm(weight, reps):
    return weight * (1 + reps / 30.0)

# Activation functions
def sigmoid(x):
    # Clamp x to avoid math overflow
    x = max(-500, min(500, x))
    return 1.0 / (1.0 + math.exp(-x))

def sigmoid_derivative(x):
    return x * (1.0 - x)

class PureMLP:
    def __init__(self, input_nodes, hidden_nodes, output_nodes):
        self.input_nodes = input_nodes
        self.hidden_nodes = hidden_nodes
        self.output_nodes = output_nodes
        
        # Initialize weights with random values between -0.5 and 0.5
        random.seed(42)
        self.weights_ih = [[random.uniform(-0.5, 0.5) for _ in range(self.hidden_nodes)] for _ in range(self.input_nodes)]
        self.weights_ho = [[random.uniform(-0.5, 0.5) for _ in range(self.output_nodes)] for _ in range(self.hidden_nodes)]
        
        self.bias_h = [random.uniform(-0.5, 0.5) for _ in range(self.hidden_nodes)]
        self.bias_o = [random.uniform(-0.5, 0.5) for _ in range(self.output_nodes)]
        
    def feedforward(self, inputs):
        # Hidden layer
        hidden_inputs = [0.0] * self.hidden_nodes
        for j in range(self.hidden_nodes):
            sum_h = self.bias_h[j]
            for i in range(self.input_nodes):
                sum_h += inputs[i] * self.weights_ih[i][j]
            hidden_inputs[j] = sigmoid(sum_h)
            
        # Output layer
        output_inputs = [0.0] * self.output_nodes
        for k in range(self.output_nodes):
            sum_o = self.bias_o[k]
            for j in range(self.hidden_nodes):
                sum_o += hidden_inputs[j] * self.weights_ho[j][k]
            output_inputs[k] = sum_o # Linear output for regression
            
        return output_inputs, hidden_inputs
        
    def train(self, X, y, epochs=1000, lr=0.01):
        for epoch in range(epochs):
            for i in range(len(X)):
                inputs = X[i]
                target = y[i]
                
                outputs, hidden = self.feedforward(inputs)
                output = outputs[0]
                
                # Mean Squared Error derivative for linear output: (output - target)
                error = output - target
                
                # Backprop to hidden-output weights
                delta_o = error # linear activation derivative is 1
                
                for j in range(self.hidden_nodes):
                    self.weights_ho[j][0] -= lr * delta_o * hidden[j]
                self.bias_o[0] -= lr * delta_o
                
                # Backprop to input-hidden weights
                for j in range(self.hidden_nodes):
                    delta_h = delta_o * self.weights_ho[j][0] * sigmoid_derivative(hidden[j])
                    for k in range(self.input_nodes):
                        self.weights_ih[k][j] -= lr * delta_h * inputs[k]
                    self.bias_h[j] -= lr * delta_h

def normalize(data):
    if not data: return data, [], []
    cols = list(zip(*data))
    mins = [min(col) for col in cols]
    maxs = [max(col) for col in cols]
    
    ranges = [maxs[i] - mins[i] if maxs[i] - mins[i] > 0 else 1.0 for i in range(len(cols))]
    
    norm_data = []
    for row in data:
        norm_row = [(row[i] - mins[i]) / ranges[i] for i in range(len(row))]
        norm_data.append(norm_row)
        
    return norm_data, mins, ranges

def extract_features(workouts):
    if not workouts:
        return None, None, None

    workouts = sorted(workouts, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))
    
    X = []
    y = []
    
    for i in range(1, len(workouts)):
        prev_w = workouts[i-1]
        curr_w = workouts[i]
        
        prev_date = datetime.strptime(prev_w['date'], '%Y-%m-%d')
        curr_date = datetime.strptime(curr_w['date'], '%Y-%m-%d')
        days_rested = (curr_date - prev_date).days
        
        rolling_volume = prev_w.get('sets', 1) * prev_w.get('reps', 1) * float(prev_w.get('weight_kg', 0))
        current_1rm = calculate_1rm(float(prev_w.get('weight_kg', 0)), int(prev_w.get('reps', 1)))
        
        X.append([rolling_volume, days_rested, current_1rm])
        y.append(float(curr_w.get('weight_kg', 0)))
        
    last_w = workouts[-1]
    last_date = datetime.strptime(last_w['date'], '%Y-%m-%d')
    days_since_last = max((datetime.now() - last_date).days, 1)
    
    last_volume = last_w.get('sets', 1) * last_w.get('reps', 1) * float(last_w.get('weight_kg', 0))
    last_1rm = calculate_1rm(float(last_w.get('weight_kg', 0)), int(last_w.get('reps', 1)))
    
    next_features = [[last_volume, days_since_last, last_1rm]]
    
    if len(X) == 0:
        return [], [], next_features
        
    return X, y, next_features

def predict_next_weight(workouts):
    valid_workouts = [w for w in workouts if 'weight_kg' in w and 'reps' in w and 'sets' in w]
    
    if len(valid_workouts) < 5:
        if not valid_workouts:
            return 20.0, False, 0.0
            
        last_w = valid_workouts[-1]
        base_w = float(last_w.get('weight_kg', 0))
        reps = int(last_w.get('reps', 0))
        
        suggested = base_w + 2.5 if reps >= 8 else base_w
        return round(suggested, 1), False, 0.50
        
    X, y, next_features = extract_features(valid_workouts)
    
    if len(X) < 4:
         last_w = valid_workouts[-1]
         base_w = float(last_w.get('weight_kg', 0))
         return round(base_w + 2.5, 1), False, 0.50

    # Normalize X
    norm_X, mins_X, ranges_X = normalize(X)
    
    # Normalize y
    y_min = min(y)
    y_max = max(y)
    y_range = y_max - y_min if y_max - y_min > 0 else 1.0
    norm_y = [(val - y_min) / y_range for val in y]
    
    # Train
    mlp = PureMLP(input_nodes=3, hidden_nodes=6, output_nodes=1)
    mlp.train(norm_X, norm_y, epochs=1500, lr=0.05)
    
    # Predict
    norm_next = [[(next_features[0][i] - mins_X[i]) / ranges_X[i] for i in range(3)]]
    pred_norm, _ = mlp.feedforward(norm_next[0])
    
    # Denormalize prediction
    pred_weight = (pred_norm[0] * y_range) + y_min
    
    last_weight = float(valid_workouts[-1].get('weight_kg', 0))
    plateau_risk = bool(pred_weight <= last_weight + 0.5 and len(valid_workouts) >= 8)
    
    # Calculate a rough pseudo-R2 on training data for confidence
    preds = [mlp.feedforward(x)[0][0] for x in norm_X]
    ss_res = sum((norm_y[i] - preds[i])**2 for i in range(len(norm_y)))
    y_mean = sum(norm_y) / len(norm_y) if len(norm_y) > 0 else 0
    ss_tot = sum((norm_y[i] - y_mean)**2 for i in range(len(norm_y)))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.5
    
    confidence = max(0.1, min(r2, 0.95))
    
    suggested = round(pred_weight * 2) / 2
    suggested = max(last_weight * 0.8, suggested) # Floor at 80% of last weight to prevent wild negatives
    
    return float(suggested), plateau_risk, round(float(confidence), 2)
