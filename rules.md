Rule 1:

When two consecutive bearish (down/red) candles appear next to each other, check the following two conditions:

The upper wick (high wick) of the second candle is higher than the upper wick of the first candle.
The lower wick of the second candle is also higher than the lower wick of the first candle.

If both conditions are met, we expect the next candle to be bullish (green/up).

Or, in a more technical trading style:

Bullish Reversal Rule

If there are two consecutive bearish candles:

The second candle's upper wick is higher than the first candle's upper wick.
The second candle's lower wick is higher than the first candle's lower wick.

When both conditions are satisfied, it indicates bullish strength, and the expectation is that the next candle will be bullish (green/up).

~~~
{"version":2,"conditions":[
  {"type":"pattern","params":{"consecutive":2,"direction":"bearish"}},
  {"type":"wick_comparison","params":{"candle_a":-2,"candle_b":-1,"part":"upper","comparison":"gt"}},
  {"type":"wick_comparison","params":{"candle_a":-2,"candle_b":-1,"part":"lower","comparison":"gt"}}
],"action":"bullish"}
~~~