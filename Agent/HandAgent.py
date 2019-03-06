import random
import math
import numpy as np

from SupportAlgorithm.MoveAction import MoveAction
from util import Grid

class HandAgent():
    def __init__(self):
        self.target = (random.random()*8.0, random.random()*5.0)
        self.move = None
        self.ctr = 0

    def reset(self):
        self.move = None
        self.ctr = 0

    def select_action(self, state):
        action = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        pos = (state[0], state[1])
        vel = (state[2], state[3])
        angle = state[4]
        if state[-1] > 0 and state[-3] > 0:
            action[4] = +1.0
        else:
            action[4] = 0.0
        if self.ctr % 5 == 0:
            if state[-1] > 0 and state[-3] > 0:
                self.target = (state[-4], state[-3])
                if self.move is None or ((pos[0]-self.target[0])**2 + (pos[1]-self.target[1])**2 > 4):
                    self.move = MoveAction(self.target, pos, vel, angle)
            else:
                if self.move is None or ((pos[0]-self.target[0])**2 + (pos[1]-self.target[1])**2 < 4):
                    self.target = (random.random()*8.0, random.random()*5.0)
                    #print(self.target)
                    self.move = MoveAction(self.target, pos, vel, angle)
        self.ctr += 1

        new_action = self.move.MoveTo(pos, vel, angle, action)

        return new_action