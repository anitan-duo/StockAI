'use client';

import { cn, formatPercent, formatPrice } from '@/lib/utils';
import type { Prediction } from '@/types';
import { ProbabilityBarGroup } from './probability-bar';
import { Card, CardContent, CardHeader, CardTitle } from './card';
import { Badge } from './badge';
import { TrendingUp, TrendingDown, Minus, Target, Calendar, Brain } from 'lucide-react';

interface PredictionCardProps {
  prediction: Prediction;
  symbol: string;
  name?: string;
  price?: number;
  changePercent?: number;
  compact?: boolean;
  className?: string;
}

export function PredictionCard({ 
  prediction, 
  symbol, 
  name,
  price,
  changePercent,
  compact = false,
  className 
}: PredictionCardProps) {
  const directionColors = {
    up: 'text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30',
    neutral: 'text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/30',
    down: 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30',
  };
  
  const directionIcons = {
    up: TrendingUp,
    neutral: Minus,
    down: TrendingDown,
  };
  
  const DirectionIcon = directionIcons[prediction.direction];
  
  if (compact) {
    return (
      <div className={cn('p-3 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700', className as string)}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-semibold text-gray-900 dark:text-white">{symbol}</div>
            {name && <div className="text-xs text-gray-500 dark:text-gray-400">{name}</div>}
          </div>
          <Badge variant="outline" className={cn(directionColors[prediction.direction], 'text-xs')}>
            {prediction.direction.toUpperCase()} {prediction.probabilities.up}%
          </Badge>
        </div>
        
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-lg font-bold text-gray-900 dark:text-white tabular-nums">
              {price ? formatPrice(price) : '—'}
            </div>
            {changePercent !== undefined && (
              <div className={cn('text-xs font-medium', changePercent >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')}>
                {formatPercent(changePercent)}
              </div>
            )}
          </div>
          <div className="border-x border-gray-200 dark:border-gray-700">
            <div className="text-lg font-bold text-gray-900 dark:text-white tabular-nums">
              ER: {prediction.expectedReturn >= 0 ? '+' : ''}{prediction.expectedReturn.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Expected Return</div>
          </div>
          <div>
            <div className="text-lg font-bold text-gray-900 dark:text-white tabular-nums">{prediction.confidence}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Confidence</div>
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <Card className={cn('overflow-hidden', className as string)}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-lg">{symbol}</CardTitle>
            {name && <p className="text-sm text-gray-500 dark:text-gray-400">{name}</p>}
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={cn(directionColors[prediction.direction], 'gap-1')}>
              <DirectionIcon className="h-3 w-3" />
              {prediction.direction.toUpperCase()} {prediction.probabilities.up}%
            </Badge>
            <span className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded">
              {prediction.horizon}
            </span>
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-4 pb-0">
        {price !== undefined && changePercent !== undefined && (
          <div className="flex items-baseline justify-between p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
            <div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">{formatPrice(price)}</div>
              <div className={cn('text-sm font-medium', changePercent >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')}>
                {changePercent >= 0 ? '+' : ''}{formatPercent(changePercent)}
              </div>
            </div>
          </div>
        )}
        
        <div className="grid grid-cols-3 gap-4 p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">
              {prediction.expectedReturn >= 0 ? '+' : ''}{prediction.expectedReturn.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Expected Return</div>
          </div>
          <div className="border-x border-gray-200 dark:border-gray-700 text-center">
            <div className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">{prediction.confidence}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Confidence</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">
              {formatPercent(prediction.expectedRange.low)} → {formatPercent(prediction.expectedRange.high)}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Expected Range</div>
          </div>
        </div>
        
        <div>
          <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Probability Distribution</div>
          <ProbabilityBarGroup probabilities={prediction.probabilities} />
        </div>
        
        <div className="pt-2 border-t border-gray-200 dark:border-gray-700 space-y-2 text-xs">
          <div className="flex items-center justify-between text-gray-600 dark:text-gray-400">
            <span className="flex items-center gap-1"><Brain className="h-3 w-3" /> Model</span>
            <span className="font-medium text-gray-900 dark:text-white">{prediction.modelVersion}</span>
          </div>
          <div className="flex items-center justify-between text-gray-600 dark:text-gray-400">
            <span className="flex items-center gap-1"><Calendar className="h-3 w-3" /> Data</span>
            <span className="font-medium text-gray-900 dark:text-white">{new Date(prediction.dataTimestamp).toLocaleString()}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface PredictionCardDetailedProps extends PredictionCardProps {
  onViewDetails?: () => void;
}

export function PredictionCardDetailed({ 
  prediction, 
  symbol, 
  name,
  price,
  changePercent,
  onViewDetails,
  className 
}: PredictionCardDetailedProps) {
  return (
    <div className={cn(className)}>
      <PredictionCard 
        prediction={prediction} 
        symbol={symbol} 
        name={name}
        price={price}
        changePercent={changePercent}
      />
      {onViewDetails && (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onViewDetails}
            className="w-full text-sm font-medium text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 flex items-center justify-center gap-1"
          >
            View Analysis
            <Target className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}