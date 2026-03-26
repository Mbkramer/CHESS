import torch
import torch.nn as nn
import torch.nn.functional as F
import os

class ChessNet(nn.Module):
    """
    NNUE-style evaluation network.

    Input:  (batch, 12, 8, 8) tensor — one plane per piece type
    Output: (batch, 1) scalar — positive = good for white, negative = good for black

    Architecture:
        3 convolutional layers to understand local piece patterns
        2 fully connected layers to score the whole position
        tanh output bounded to [-1, 1]

    Training target:
        +1.0 = white won
        -1.0 = black won
         0.0 = draw
    """

    def __init__(self):
        super().__init__()

        # Conv layers — learn local piece patterns
        # 12 input planes (one per piece type), 64 filters each
        self.conv1 = nn.Conv2d(13,  64, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(128, 128, kernel_size=3, padding=1)

        self.bn1 = nn.BatchNorm2d(64)
        self.bn2 = nn.BatchNorm2d(128)
        self.bn3 = nn.BatchNorm2d(128)

        # Fully connected layers — combine everything into a score
        self.fc1 = nn.Linear(128 * 8 * 8, 256)
        self.fc2 = nn.Linear(256, 64)
        self.fc3 = nn.Linear(64, 1)

        self.dropout = nn.Dropout(p=0.3)

    def forward(self, x):
        # Convolutional feature extraction
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = F.relu(self.bn3(self.conv3(x)))

        # Flatten to 1D
        x = x.view(x.size(0), -1)

        # Fully connected scoring
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = F.relu(self.fc2(x))
        x = torch.tanh(self.fc3(x))   # bounded [-1, 1]

        return x


def save_model(model, path='check_points/chess_model.pt'):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    torch.save(model.state_dict(), path)
    print(f"Model saved to {path}")

def load_model(path='check_points/chess_model.pt'):
    model = ChessNet()
    model.load_state_dict(torch.load(path, map_location='cpu'))
    model.eval()
    print(f"Model loaded from {path}")
    return model


if __name__ == "__main__":
    import torch
    model = ChessNet()

    # Count parameters
    total = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {total:,}")

    # Test forward pass
    dummy = torch.zeros(1, 13, 8, 8)   # was (1, 12, 8, 8)
    out = model(dummy)
    print(f"Output shape: {out.shape}")
    print(f"Output value (untrained): {out.item():.4f}")