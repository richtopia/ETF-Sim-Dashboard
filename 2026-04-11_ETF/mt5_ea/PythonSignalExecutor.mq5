//+------------------------------------------------------------------+
//|                                     PythonSignalExecutor.mq5     |
//|                    Executes exported Python weights in MT5       |
//+------------------------------------------------------------------+
#property copyright "Signal Bridge"
#property link      ""
#property version   "1.00"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input string InpFileName = "mt5_signals.csv"; // Signal CSV File (place in MQL5\Files)
input string InpSymbolSuffix = "";            // Broker suffix (e.g. ".US")

CTrade trade;
CPositionInfo posInfo;

// Structure to hold our daily targets
struct TargetWeight {
    string symbol;
    double weight;
};

// Global variables
datetime g_lastRebalance = 0;
TargetWeight g_currentTargets[];
int g_targetCount = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("Initializing Python Signal Executor...");
    trade.SetExpertMagicNumber(1337);
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Print("Deinitializing...");
}

//+------------------------------------------------------------------+
//| Read signals for a specific date from the CSV file               |
//+------------------------------------------------------------------+
bool LoadTargetsForDate(datetime currentDate)
{
    string dateStr = TimeToString(currentDate, TIME_DATE); // YYYY.MM.DD
    StringReplace(dateStr, ".", "-");                      // Convert to YYYY-MM-DD
    
    int fileHandle = FileOpen(InpFileName, FILE_READ|FILE_CSV|FILE_ANSI, ',');
    if(fileHandle == INVALID_HANDLE)
    {
        Print("Could not open file: ", InpFileName, " Error: ", GetLastError());
        return false;
    }
    
    // Clear current targets
    ArrayResize(g_currentTargets, 0);
    g_targetCount = 0;
    
    // Skip header
    if(!FileIsEnding(fileHandle)) FileReadString(fileHandle); // Date
    if(!FileIsEnding(fileHandle)) FileReadString(fileHandle); // Symbol
    if(!FileIsEnding(fileHandle)) FileReadString(fileHandle); // Weight
    
    bool foundTargets = false;
    
    while(!FileIsEnding(fileHandle))
    {
        string rowDate = FileReadString(fileHandle);
        if (rowDate == "") break;
        string rowSymbol = FileReadString(fileHandle);
        string rowWeightStr = FileReadString(fileHandle);
        
        if (rowDate == dateStr)
        {
            foundTargets = true;
            ArrayResize(g_currentTargets, g_targetCount + 1);
            g_currentTargets[g_targetCount].symbol = rowSymbol + InpSymbolSuffix;
            g_currentTargets[g_targetCount].weight = StringToDouble(rowWeightStr);
            g_targetCount++;
        }
    }
    
    FileClose(fileHandle);
    return foundTargets;
}

//+------------------------------------------------------------------+
//| Rebalance the portfolio to match new targets                     |
//+------------------------------------------------------------------+
void ExecuteRebalance()
{
    Print("Rebalancing for ", g_targetCount, " targets.");
    
    // 1. Close positions that are not in target list
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(posInfo.SelectByIndex(i))
        {
            string posSymbol = posInfo.Symbol();
            bool isTarget = false;
            for(int j = 0; j < g_targetCount; j++)
            {
                if(g_currentTargets[j].symbol == posSymbol)
                {
                    isTarget = true;
                    break;
                }
            }
            
            if(!isTarget)
            {
                trade.PositionClose(posSymbol);
                Print("Closed position: ", posSymbol);
            }
        }
    }
    
    // 2. Open new positions up to correct weight
    double accountEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    
    for(int i = 0; i < g_targetCount; i++)
    {
        string sym = g_currentTargets[i].symbol;
        double targetAlloc = accountEquity * g_currentTargets[i].weight;
        
        // Select symbol and ensure market watch
        if(!SymbolSelect(sym, true)) {
            Print("Unknown symbol: ", sym);
            continue;
        }
        
        double currentPrice = SymbolInfoDouble(sym, SYMBOL_ASK);
        if (currentPrice <= 0) continue;
        
        double targetVolume = targetAlloc / currentPrice;
        
        // Very basic execution: if we don't have it, buy it.
        // True dynamic rebalancing would check existing volume, but this is simplified.
        bool hasPosition = false;
        long posType = -1;
        
        if (PositionSelect(sym)) {
            hasPosition = true;
            // Existing position can be adjusted if needed, but omitted for brevity
        }
        
        if(!hasPosition)
        {
            // Floor volume to step
            double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
            double minV = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
            double vol = MathFloor(targetVolume / step) * step;
            
            if (vol >= minV) {
                trade.Buy(vol, sym);
                Print("Bought ", vol, " of ", sym);
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
    // We only check once per day for new signals
    datetime currentDay = iTime(Symbol(), PERIOD_D1, 0);
    
    if (currentDay != g_lastRebalance)
    {
        if (LoadTargetsForDate(currentDay))
        {
            ExecuteRebalance();
            g_lastRebalance = currentDay;
        }
        else
        {
            // If no signal for today, we might just update lastRebalance so we don't spam file read
            // Note: If you want to hold on days without target updates, just run this once.
            g_lastRebalance = currentDay; 
        }
    }
}
//+------------------------------------------------------------------+
